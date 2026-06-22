"""Interactive terminal dashboard for the Bybit bot.

Stdlib HTTP server (no extra deps). Reads the engine's state.json plus a few live
extras from the in-process Engine (scanner ranking, halt status, controls).

  GET  /            -> the UI (single self-contained page)
  GET  /api/state   -> JSON: KPIs, positions (with R + stop distance), scanner, controls
  GET  /api/export  -> full uncapped trade history
  POST /api/control -> {action: pause|resume|flatten|block|unblock, symbol?}

  python3 -m bybitbot.dashboard --port 8787 --state bybit_state.json
"""
import os
import sys
import json
import time
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Config
from .control import CONTROL

_START = time.time()
STATE_PATH = "bybit_state.json"
ENGINE = None                      # set by serve.py for live scanner/halt extras

# ---- auth (mirrors copytrader) -------------------------------------------
_PASSWORD = os.environ.get("PASSWORD", "password123")
_sessions = {}
_SESSION_TTL = 86400 * 7
_sessions_lock = threading.Lock()


def _new_session():
    token = secrets.token_hex(32)
    with _sessions_lock:
        _sessions[token] = time.time()
    return token


def _valid_session(token):
    with _sessions_lock:
        created = _sessions.get(token)
    if created is None:
        return False
    if time.time() - created > _SESSION_TTL:
        with _sessions_lock:
            _sessions.pop(token, None)
        return False
    return True


def _parse_cookie(raw):
    out = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def _read_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def build_state(cfg):
    s = _read_state()
    base = cfg.account_size
    uptime = int(time.time() - _START)
    mode = cfg.mode
    scanner = ENGINE.scanner if ENGINE else []
    halt = ENGINE.halt_reason if ENGINE else ""
    ctrl = CONTROL.snapshot()

    empty_kpis = {"equity": base, "balance": base, "open_notional": 0, "unrealized": 0,
                  "realized": 0, "open_positions": 0, "closed_trades": 0, "win_rate": 0,
                  "profit_factor": 0, "max_dd": 0, "winners": 0, "losers": 0, "ret_pct": 0,
                  "day_pnl": 0, "best": 0, "worst": 0}
    if not s:
        return {"live": False, "mode": mode, "account_size": base, "halt": halt,
                "control": ctrl, "scanner": scanner, "positions": [], "closed": [],
                "history": [], "activity": [], "updated": time.time(), "uptime": uptime,
                "kpis": empty_kpis}

    positions = []
    open_notional = unrealized = 0.0
    winners = losers = 0
    for p in s.get("positions", {}).values():
        side = p.get("side", 1)
        cur = p["cur_price"] if p.get("cur_price", 0) > 0 else p["entry"]
        upnl = (cur - p["entry"]) * p["qty"] * side
        val = p["qty"] * cur
        open_notional += val
        unrealized += upnl
        winners += upnl > 0
        losers += upnl < 0
        rd = p.get("risk_dist", 0) or 1e-9
        r_now = (cur - p["entry"]) * side / rd
        stop = p.get("stop", p["entry"])
        # distance from price to stop, as a fraction of price (0 = at stop)
        dist = abs(cur - stop) / cur if cur else 0
        positions.append({
            "symbol": p["symbol"], "side": "long" if side > 0 else "short",
            "qty": p["qty"], "entry": p["entry"], "cur": cur, "stop": stop,
            "value": val, "upnl": upnl,
            "upnl_pct": (cur / p["entry"] - 1.0) * 100 * side if p["entry"] else 0.0,
            "r": r_now, "peak_r": p.get("peak_r", 0.0), "adds": p.get("adds", 0),
            "stop_dist_pct": dist * 100, "age": int(time.time() - p.get("opened_t", time.time())),
            "score": p.get("score", 0),
        })
    positions.sort(key=lambda x: x["upnl"], reverse=True)

    closed_all = s.get("closed", [])
    wins = [c for c in closed_all if c["pnl"] > 0]
    losses = [c for c in closed_all if c["pnl"] <= 0]
    win_rate = len(wins) / len(closed_all) if closed_all else 0.0
    gross_win = sum(c["pnl"] for c in wins)
    gross_loss = abs(sum(c["pnl"] for c in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (gross_win and 99.9)
    activity = [{"symbol": c.get("symbol", ""), "reason": c.get("reason", ""),
                 "pnl": c["pnl"], "side": c.get("side", ""), "exit": c.get("exit", 0)}
                for c in reversed(closed_all[-25:])]

    history = s.get("history", [])
    peak, mdd = -1e9, 0.0
    for h in history:
        peak = max(peak, h["equity"])
        if peak > 0:
            mdd = min(mdd, h["equity"] / peak - 1.0)

    balance = s.get("balance", base)
    realized = s.get("realized_pnl", 0.0)
    equity = balance + unrealized
    total = realized + unrealized

    return {
        "live": True, "mode": mode, "account_size": base, "halt": halt,
        "control": ctrl, "scanner": scanner, "updated": time.time(), "uptime": uptime,
        "positions": positions, "closed": list(reversed(closed_all))[:40],
        "activity": activity, "history": history[-400:],
        "kpis": {
            "equity": equity, "balance": balance, "open_notional": open_notional,
            "unrealized": unrealized, "realized": realized, "total": total,
            "ret_pct": total / base * 100 if base else 0.0,
            "open_positions": len(positions), "closed_trades": len(closed_all),
            "win_rate": win_rate, "profit_factor": profit_factor or 0.0,
            "max_dd": mdd * 100, "winners": winners, "losers": losers,
            "day_pnl": s.get("day_realized", 0.0),
            "best": positions[0]["upnl"] if positions else 0.0,
            "worst": positions[-1]["upnl"] if positions else 0.0,
        },
    }


def export_state(cfg):
    bs = build_state(cfg)
    s = _read_state() or {}
    return {"account_size": bs["account_size"], "mode": bs["mode"], "kpis": bs["kpis"],
            "uptime": bs.get("uptime"), "open": bs["positions"], "closed": s.get("closed", [])}


def handle_control(params):
    action = params.get("action", [""])[0]
    symbol = params.get("symbol", [""])[0]
    if action == "pause":
        CONTROL.set_paused(True)
    elif action == "resume":
        CONTROL.set_paused(False)
    elif action == "flatten":
        CONTROL.request_flatten()
    elif action == "block" and symbol:
        CONTROL.block(symbol)
    elif action == "unblock" and symbol:
        CONTROL.unblock(symbol)
    else:
        return {"ok": False, "error": "unknown action"}
    return {"ok": True, "control": CONTROL.snapshot()}


class Handler(BaseHTTPRequestHandler):
    cfg = Config()

    def log_message(self, *a):
        pass

    def _authenticated(self):
        cookies = _parse_cookie(self.headers.get("Cookie", ""))
        return _valid_session(cookies.get("session", ""))

    def _send(self, body, ctype="application/json", extra_headers=()):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra_headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location, extra_headers=()):
        self.send_response(302)
        self.send_header("Location", location)
        for k, v in extra_headers:
            self.send_header(k, v)
        self.end_headers()

    def _unauth(self):
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"unauthenticated"}')

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/login":
            self._send(LOGIN_PAGE, "text/html; charset=utf-8")
        elif path.startswith("/api/state"):
            if not self._authenticated():
                self._unauth()
            else:
                self._send(json.dumps(build_state(self.cfg)))
        elif path.startswith("/api/export"):
            if not self._authenticated():
                self._unauth()
            else:
                self._send(json.dumps(export_state(self.cfg)))
        elif path == "/" or path.startswith("/index"):
            if self._authenticated():
                self._send(PAGE, "text/html; charset=utf-8")
            else:
                self._redirect("/login")
        elif path.startswith("/manifest"):
            self._send(MANIFEST, "application/manifest+json")
        elif path.startswith("/sw.js"):
            self._send(SW, "application/javascript")
        elif path.startswith("/icon.svg"):
            self._send(ICON, "image/svg+xml")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        if path == "/login":
            params = parse_qs(body)
            if params.get("password", [""])[0] == _PASSWORD:
                token = _new_session()
                cookie = f"session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={_SESSION_TTL}"
                self._redirect("/", extra_headers=[("Set-Cookie", cookie)])
            else:
                self._send(LOGIN_PAGE.replace("<!--ERROR-->",
                           '<p class="err">Incorrect password. Try again.</p>'),
                           "text/html; charset=utf-8")
        elif path == "/api/control":
            if not self._authenticated():
                self._unauth()
            else:
                self._send(json.dumps(handle_control(parse_qs(body))))
        else:
            self.send_response(404)
            self.end_headers()


LOGIN_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>BYBIT BOT // LOGIN</title>
<style>
  :root{--bg:#05070a;--accent:#16d39a;--dim:#5a6b78;--txt:#cfe3e0;--line:#16242e;--red:#ff4d5e;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);font:13px/1.5 "SF Mono",Menlo,Consolas,monospace;
       display:flex;align-items:center;justify-content:center;min-height:100vh;}
  .box{border:1px solid var(--line);padding:36px 40px;width:100%;max-width:360px;background:#0a0f14;border-radius:8px;}
  .logo{color:var(--accent);font-weight:700;font-size:16px;letter-spacing:1px;margin-bottom:6px;}
  .sub{color:var(--dim);font-size:11px;margin-bottom:28px;}
  label{display:block;color:var(--dim);font-size:10px;text-transform:uppercase;margin-bottom:6px;}
  input{width:100%;background:#05070a;border:1px solid var(--line);color:var(--txt);
        padding:10px;font:13px/1 monospace;outline:none;margin-bottom:18px;border-radius:4px;}
  input:focus{border-color:var(--accent);}
  button{width:100%;background:var(--accent);color:#04110d;border:none;padding:11px;
         font:700 13px/1 monospace;cursor:pointer;border-radius:4px;}
  .err{color:var(--red);font-size:11px;margin-bottom:14px;}
</style></head><body>
<div class="box">
  <div class="logo">⚡ BYBIT BOT</div>
  <div class="sub">AUTONOMOUS TRADING TERMINAL — AUTH REQUIRED</div>
  <!--ERROR-->
  <form method="POST" action="/login">
    <label>Password</label>
    <input type="password" name="password" autofocus autocomplete="current-password">
    <button type="submit">ENTER →</button>
  </form>
</div></body></html>"""

MANIFEST = json.dumps({
    "name": "Bybit Bot Terminal", "short_name": "BybitBot",
    "start_url": "/", "display": "standalone", "background_color": "#05070a",
    "theme_color": "#16d39a",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}],
})

SW = r"""const C='bb-v1';
self.addEventListener('install',e=>{self.skipWaiting();});
self.addEventListener('activate',e=>{self.clients.claim();});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);
  if(u.pathname.startsWith('/api/'))return;
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});
"""

ICON = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="96" fill="#0a0f14"/>
<rect x="28" y="28" width="456" height="456" rx="72" fill="none" stroke="#16d39a" stroke-width="14"/>
<polyline points="80,340 160,300 220,330 290,230 350,260 432,140" fill="none" stroke="#16d39a" stroke-width="18" stroke-linejoin="round" stroke-linecap="round"/>
<text x="256" y="440" font-family="monospace" font-size="90" font-weight="bold" fill="#16d39a" text-anchor="middle">BYBIT</text>
</svg>
"""

PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>BYBIT BOT // TERMINAL</title>
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#16d39a">
<link rel="apple-touch-icon" href="/icon.svg"><link rel="icon" href="/icon.svg">
<style>
  :root{--bg:#05070a;--panel:#0a0f14;--accent:#16d39a;--grn:#16d39a;--red:#ff4d5e;
        --amber:#ffb547;--dim:#5a6b78;--txt:#cfe3e0;--line:#16242e;--cyan:#36c5e0;--blue:#3b82f6;}
  *{box-sizing:border-box}html,body{margin:0}
  body{background:var(--bg);color:var(--txt);overflow-x:hidden;
       font:12px/1.4 "SF Mono",Menlo,Consolas,monospace;}
  .bar{display:flex;align-items:center;gap:12px;background:#0a0f14;flex-wrap:wrap;
       border-bottom:2px solid var(--accent);padding:8px 12px;font-weight:700;}
  .bar .logo{color:var(--accent);font-size:14px;letter-spacing:.5px}
  .badge{padding:2px 8px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:.5px}
  .badge.testnet{background:#13343b;color:var(--cyan);border:1px solid var(--cyan)}
  .badge.paper{background:#2a2410;color:var(--amber);border:1px solid var(--amber)}
  .badge.live{background:#3a1118;color:var(--red);border:1px solid var(--red)}
  .badge.halt{background:#3a1118;color:var(--red);border:1px solid var(--red)}
  .bar .sp{flex:1}
  .led{animation:pulse 1.6s ease-in-out infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .btn{background:#13242e;border:1px solid var(--line);color:var(--txt);padding:5px 11px;
       border-radius:4px;cursor:pointer;font:11px/1 monospace;font-weight:700}
  .btn:hover{border-color:var(--accent)}
  .btn.danger{border-color:var(--red);color:var(--red)}
  .btn.warn{border-color:var(--amber);color:var(--amber)}
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line)}
  .kpi{background:var(--panel);padding:8px 11px}
  .kpi .k{color:var(--dim);font-size:9.5px;text-transform:uppercase;letter-spacing:.5px}
  .kpi .v{font-size:18px;font-weight:700;margin-top:3px;white-space:nowrap}
  .grid{display:grid;grid-template-columns:1.5fr 1fr;gap:1px;background:var(--line)}
  .col{display:flex;flex-direction:column;gap:1px;background:var(--line);min-width:0}
  .panel{background:var(--panel);min-width:0;overflow:hidden}
  .ph{color:var(--accent);background:#0c141a;padding:6px 11px;font-weight:700;letter-spacing:.6px;
      border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
  .ph .c{color:var(--dim);font-weight:400;font-size:10px}
  .tw{overflow-x:auto}table{width:100%;border-collapse:collapse}
  th{color:var(--dim);text-align:right;font-weight:400;font-size:9.5px;text-transform:uppercase;
     padding:4px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
  th.l,td.l{text-align:left}
  td{padding:5px 9px;border-bottom:1px solid #0f1a20;text-align:right;white-space:nowrap}
  tr.clk{cursor:pointer}tr.clk:hover td{background:#0f1c22}
  .pos{color:var(--grn)}.neg{color:var(--red)}.am{color:var(--amber)}.mut{color:var(--dim)}.cy{color:var(--cyan)}
  .chartwrap{padding:10px}svg.eq{width:100%;height:170px;display:block}
  .sbar{height:7px;background:#0f1a20;border:1px solid var(--line);border-radius:3px;position:relative;overflow:hidden}
  .sfill{height:100%;position:absolute;top:0;left:0;background:var(--accent)}
  .pill{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700}
  .pill.long{background:#0e2a22;color:var(--grn)}.pill.short{background:#2a1116;color:var(--red)}
  .scan-row{display:grid;grid-template-columns:auto 1fr auto auto;gap:8px;align-items:center;
            padding:4px 11px;border-bottom:1px solid #0f1a20}
  .act{padding:4px 11px;border-bottom:1px solid #0f1a20;display:flex;gap:8px;align-items:baseline}
  .act .rsn{color:var(--dim);min-width:90px}
  .empty{color:var(--dim);padding:11px}
  .foot{background:#0a0f14;border-top:1px solid var(--line);color:var(--dim);padding:5px 12px;
        display:flex;gap:16px;flex-wrap:wrap;font-size:11px}
  /* pop-out drawer */
  .drawer{position:fixed;top:0;right:0;width:420px;max-width:92vw;height:100%;background:#0a0f14;
          border-left:2px solid var(--accent);transform:translateX(100%);transition:transform .22s ease;
          z-index:80;overflow-y:auto;box-shadow:-8px 0 30px rgba(0,0,0,.5)}
  .drawer.open{transform:translateX(0)}
  .drawer .dh{display:flex;justify-content:space-between;align-items:center;padding:12px;
              border-bottom:1px solid var(--line)}
  .drawer .dh .x{cursor:pointer;color:var(--dim);font-size:18px;font-weight:700}
  .dkv{display:grid;grid-template-columns:1fr auto;gap:3px 10px;padding:12px}
  .dkv .lbl{color:var(--dim)}
  .scrim{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:79;opacity:0;pointer-events:none;transition:opacity .2s}
  .scrim.open{opacity:1;pointer-events:auto}
  @media(max-width:880px){.grid{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(3,1fr)}
    .kpi .v{font-size:15px}.hide-sm{display:none}}
  @media(max-width:440px){.kpis{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<div class="bar">
  <span class="logo">⚡ BYBIT BOT</span>
  <span id="modebadge" class="badge testnet">TESTNET</span>
  <span id="haltbadge" style="display:none" class="badge halt">HALTED</span>
  <span class="sp"></span>
  <button class="btn" id="pausebtn" onclick="ctl('pause')">⏸ PAUSE</button>
  <button class="btn danger" onclick="if(confirm('Close ALL open positions now?'))ctl('flatten')">✕ FLATTEN</button>
  <span id="conn" class="led" style="color:var(--accent)">● LIVE</span>
  <span id="clock" class="mut"></span>
</div>

<div class="kpis" id="kpis"></div>

<div class="grid">
  <div class="col">
    <div class="panel">
      <div class="ph">EQUITY CURVE <span class="c" id="eqsub"></span></div>
      <div class="chartwrap"><svg class="eq" id="chart" viewBox="0 0 600 170" preserveAspectRatio="none"></svg></div>
    </div>
    <div class="panel">
      <div class="ph">OPEN POSITIONS <span class="c" id="poscount"></span></div>
      <div class="tw"><table><thead><tr>
        <th class="l">SYMBOL</th><th class="l">SIDE</th><th class="hide-sm">QTY</th>
        <th class="hide-sm">ENTRY</th><th>MARK</th><th>R</th><th>uPNL</th><th>%</th>
        <th class="l">→ STOP</th>
      </tr></thead><tbody id="positions"></tbody></table></div>
    </div>
    <div class="panel">
      <div class="ph">ACTIVITY · RECENT EXITS <span class="c" id="actcount"></span></div>
      <div id="activity"></div>
    </div>
  </div>

  <div class="col">
    <div class="panel">
      <div class="ph">SCANNER · TOP SETUPS <span class="c">what the bot is watching</span></div>
      <div id="scanner"></div>
    </div>
    <div class="panel">
      <div class="ph">HEALTH · STATS</div>
      <div class="dkv" id="health"></div>
    </div>
    <div class="panel">
      <div class="ph">BLOTTER · CLOSED <span class="c" id="blcount"></span></div>
      <div class="tw"><table><thead><tr>
        <th class="l">SYMBOL</th><th class="l">SIDE</th><th>REASON</th><th>PNL</th>
      </tr></thead><tbody id="closed"></tbody></table></div>
    </div>
  </div>
</div>

<div class="foot">
  <span id="status">CONNECTING…</span><span class="sp" style="flex:1"></span>
  <span id="modefoot"></span><span id="updated"></span>
</div>

<div class="scrim" id="scrim" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
  <div class="dh"><span class="am" id="dtitle">—</span><span class="x" onclick="closeDrawer()">✕</span></div>
  <div class="dkv" id="dbody"></div>
  <div style="padding:0 12px 16px">
    <button class="btn warn" id="dblock">BLOCK THIS SYMBOL</button>
  </div>
</div>

<script>
const $=s=>document.querySelector(s);
const m2=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const m0=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString(undefined,{maximumFractionDigits:0});
const sgn=n=>n>0?'pos':(n<0?'neg':'mut');
const arr=n=>n>0?'▲':(n<0?'▼':'·');
const esc=s=>(s||'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
const dur=s=>{s=s|0;const h=(s/3600)|0,m=((s%3600)/60)|0;return h?`${h}h${m}m`:`${m}m`;};
let LAST=null, SELECTED=null;
function kpi(k,v,c){return `<div class="kpi"><div class="k">${k}</div><div class="v ${c||''}">${v}</div></div>`;}

async function ctl(action,symbol){
  await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:'action='+action+(symbol?'&symbol='+encodeURIComponent(symbol):'')});
  tick();
}
function openDrawer(sym){
  const p=(LAST.positions||[]).find(x=>x.symbol===sym);if(!p)return;
  SELECTED=sym;$('#dtitle').textContent=sym+' · '+p.side.toUpperCase();
  $('#dbody').innerHTML=[
    ['Side',`<span class="pill ${p.side}">${p.side}</span>`],
    ['Quantity',p.qty.toLocaleString(undefined,{maximumFractionDigits:6})],
    ['Entry',p.entry.toFixed(6)],['Mark',p.cur.toFixed(6)],
    ['Trailing stop',`<span class="am">${p.stop.toFixed(6)}</span>`],
    ['Distance to stop',p.stop_dist_pct.toFixed(2)+'%'],
    ['Current R',`<span class="${sgn(p.r)}">${p.r.toFixed(2)}R</span>`],
    ['Peak R',p.peak_r.toFixed(2)+'R'],
    ['Pyramid adds',p.adds],
    ['Notional',m0(p.value)],
    ['uPnL',`<span class="${sgn(p.upnl)}">${m2(p.upnl)} (${p.upnl_pct.toFixed(2)}%)</span>`],
    ['Entry score',(p.score||0).toFixed(2)],
    ['Age',dur(p.age)],
  ].map(r=>`<div class="lbl">${r[0]}</div><div>${r[1]}</div>`).join('');
  $('#dblock').onclick=()=>{ctl('block',sym);closeDrawer();};
  $('#drawer').classList.add('open');$('#scrim').classList.add('open');
}
function closeDrawer(){SELECTED=null;$('#drawer').classList.remove('open');$('#scrim').classList.remove('open');}

function render(d){
  LAST=d;const k=d.kpis,base=d.account_size,tot=(k.total!==undefined?k.total:k.realized+k.unrealized);
  const mb=$('#modebadge');mb.textContent=(d.mode||'testnet').toUpperCase();
  mb.className='badge '+(d.mode||'testnet');
  $('#haltbadge').style.display=d.halt?'inline-block':'none';
  $('#haltbadge').textContent='HALT: '+(d.halt||'').toUpperCase();
  $('#pausebtn').textContent=(d.control&&d.control.paused)?'▶ RESUME':'⏸ PAUSE';
  $('#pausebtn').onclick=()=>ctl((d.control&&d.control.paused)?'resume':'pause');

  $('#kpis').innerHTML=[
    kpi('Equity',m2(k.equity),'am'),
    kpi('Total P&L',`${arr(tot)} ${m2(tot)}`,sgn(tot)),
    kpi('Today',`${arr(k.day_pnl)} ${m2(k.day_pnl)}`,sgn(k.day_pnl)),
    kpi('Return',(k.ret_pct||0).toFixed(2)+'%',sgn(tot)),
    kpi('Win Rate',((k.win_rate||0)*100).toFixed(0)+'%',(k.win_rate>=0.5?'pos':'neg')),
    kpi('Profit Factor',(k.profit_factor||0).toFixed(2),(k.profit_factor>=1?'pos':'neg')),
    kpi('Unrealized',m2(k.unrealized),sgn(k.unrealized)),
    kpi('Realized',m2(k.realized),sgn(k.realized)),
    kpi('Exposure',m0(k.open_notional),''),
    kpi('Max DD',(k.max_dd||0).toFixed(2)+'%','neg'),
    kpi('Open',k.open_positions+'','cy'),
    kpi('Closed',k.closed_trades+'','mut'),
  ].join('');

  // positions
  $('#poscount').textContent=k.open_positions+' · '+(k.winners||0)+'W/'+(k.losers||0)+'L';
  const pb=$('#positions');
  if(!(d.positions||[]).length){pb.innerHTML='<tr><td colspan="9" class="empty">Flat — no open positions.</td></tr>';}
  else pb.innerHTML=d.positions.map(p=>{
    const fill=Math.max(2,Math.min(100,p.stop_dist_pct*12));
    return `<tr class="clk" onclick="openDrawer('${p.symbol}')">
     <td class="l am">${esc(p.symbol)}</td>
     <td class="l"><span class="pill ${p.side}">${p.side}</span></td>
     <td class="hide-sm mut">${p.qty.toLocaleString(undefined,{maximumFractionDigits:4})}</td>
     <td class="hide-sm">${p.entry.toFixed(4)}</td><td>${p.cur.toFixed(4)}</td>
     <td class="${sgn(p.r)}">${p.r.toFixed(2)}</td>
     <td class="${sgn(p.upnl)}">${m2(p.upnl)}</td>
     <td class="${sgn(p.upnl)}">${arr(p.upnl)}${Math.abs(p.upnl_pct).toFixed(1)}</td>
     <td class="l"><div class="sbar"><div class="sfill" style="width:${fill}%"></div></div></td></tr>`;}).join('');

  // scanner
  const sc=d.scanner||[];
  $('#scanner').innerHTML=sc.length?sc.map(s=>`<div class="scan-row">
     <span class="pill ${s.side>0?'long':'short'}">${s.side>0?'L':'S'}</span>
     <span class="am">${esc(s.symbol)}</span>
     <span class="mut">${s.price.toFixed(4)}</span>
     <span class="cy">${s.score.toFixed(2)}</span></div>`).join('')
    :'<div class="empty">No setups ranked yet (idle or book full).</div>';

  // health
  $('#health').innerHTML=[
    ['Mode',(d.mode||'').toUpperCase()],
    ['Halt',d.halt?`<span class="neg">${d.halt}</span>`:'<span class="pos">running</span>'],
    ['Winners / Losers',`<span class="pos">${k.winners||0}</span> / <span class="neg">${k.losers||0}</span>`],
    ['Best / Worst open',`<span class="pos">${m2(k.best||0)}</span> / <span class="neg">${m2(k.worst||0)}</span>`],
    ['Deployed',((k.open_notional/(k.equity||base))*100).toFixed(0)+'%'],
    ['Balance',m2(k.balance)],
    ['Blocked',(d.control&&d.control.blocklist||[]).join(', ')||'—'],
    ['Uptime',dur(d.uptime||0)],
  ].map(r=>`<div class="lbl">${r[0]}</div><div>${r[1]}</div>`).join('');

  // activity
  $('#actcount').textContent=(d.activity||[]).length+' shown';
  const af=$('#activity');
  if(!(d.activity||[]).length){af.innerHTML='<div class="empty">No closed trades yet.</div>';}
  else af.innerHTML=d.activity.map(a=>`<div class="act">
     <span class="rsn">${esc(a.reason)}</span>
     <span class="am">${esc(a.symbol)}</span>
     <span class="pill ${a.side}">${esc(a.side)}</span>
     <span class="sp" style="flex:1"></span>
     <span class="${sgn(a.pnl)}">${arr(a.pnl)} ${m2(a.pnl)}</span></div>`).join('');

  // blotter
  $('#blcount').textContent=k.closed_trades+' filled';
  const cb=$('#closed');
  if(!(d.closed||[]).length){cb.innerHTML='<tr><td colspan="4" class="empty">No closed trades yet.</td></tr>';}
  else cb.innerHTML=d.closed.map(c=>`<tr>
     <td class="l am">${esc(c.symbol)}</td><td class="l mut">${esc(c.side)}</td>
     <td class="mut">${esc(c.reason)}</td>
     <td class="${sgn(c.pnl)}">${m2(c.pnl)}</td></tr>`).join('');

  drawChart(d.history||[],base);
  $('#eqsub').textContent=(d.history||[]).length?(d.history.length+' pts'):'awaiting data';
  $('#status').innerHTML=d.live?'● ENGINE STATE LOADED':'○ WAITING FOR ENGINE';
  $('#modefoot').textContent='MODE '+(d.mode||'').toUpperCase();
  $('#updated').textContent='UPD '+new Date(d.updated*1000).toLocaleTimeString();
  if(SELECTED)openDrawer(SELECTED);   // keep drawer fresh while open
}

function drawChart(h,base){
  const svg=$('#chart'),W=600,H=170,pad=4;
  if(h.length<2){svg.innerHTML=`<line x1="0" y1="${H/2}" x2="${W}" y2="${H/2}" stroke="#16242e"/>`;return;}
  const eq=h.map(p=>p.equity);let lo=Math.min(...eq,base),hi=Math.max(...eq,base);
  if(hi-lo<1e-6){hi+=1;lo-=1;}
  const x=i=>pad+i*(W-2*pad)/(h.length-1),y=v=>H-pad-(v-lo)/(hi-lo)*(H-2*pad);
  const pts=eq.map((v,i)=>x(i).toFixed(1)+','+y(v).toFixed(1)).join(' ');
  const last=eq[eq.length-1],up=last>=base,col=up?'#16d39a':'#ff4d5e',by=y(base).toFixed(1);
  svg.innerHTML=`<polygon points="${pad},${H-pad} ${pts} ${(W-pad)},${H-pad}" fill="${col}" opacity="0.08"/>
    <line x1="0" y1="${by}" x2="${W}" y2="${by}" stroke="#2a3f33" stroke-dasharray="3 3"/>
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6"/>
    <circle cx="${x(eq.length-1)}" cy="${y(last)}" r="2.6" fill="${col}"/>
    <text x="6" y="13" fill="#5a6b78" font-size="10">$${hi.toLocaleString(undefined,{maximumFractionDigits:0})}</text>
    <text x="6" y="${H-4}" fill="#5a6b78" font-size="10">$${lo.toLocaleString(undefined,{maximumFractionDigits:0})}</text>`;
}

async function tick(){
  try{const r=await fetch('/api/state');
    if(r.status===401||r.status===403){location.href='/login';return;}
    render(await r.json());
    $('#conn').textContent='● LIVE';$('#conn').style.color='var(--accent)';
  }catch(e){$('#conn').textContent='● DISCONNECTED';$('#conn').style.color='var(--red)';}
}
setInterval(()=>{$('#clock').textContent=new Date().toLocaleTimeString();},1000);
tick();setInterval(tick,4000);
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
</script></body></html>"""


def main():
    global STATE_PATH
    port, host = 8787, "127.0.0.1"
    argv = sys.argv[1:]
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--state" in argv:
        STATE_PATH = argv[argv.index("--state") + 1]
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"bybit terminal up -> http://{host}:{port}   (state: {os.path.abspath(STATE_PATH)})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
