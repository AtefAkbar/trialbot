"""Bloomberg-style terminal dashboard for the copy-trader paper engine.

Stdlib HTTP server (no extra deps). Reads the engine's state.json and serves:
  GET /            -> the terminal UI (single self-contained page)
  GET /api/state   -> JSON: KPIs, open positions, blotter, equity trail, leaderboard

  python3 -m copytrader.dashboard            # serve on http://localhost:8787
  python3 -m copytrader.dashboard --port 9000 --state state.json
"""
import os
import sys
import json
import time
import secrets
import threading
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import pm_data
from .config import Config

_START = time.time()

# ---- auth ----------------------------------------------------------------
_PASSWORD = os.environ.get("PASSWORD", "password123")
_sessions: dict[str, float] = {}   # token -> created_at (epoch)
_SESSION_TTL = 86400 * 7           # 7 days
_sessions_lock = threading.Lock()


def _new_session() -> str:
    token = secrets.token_hex(32)
    with _sessions_lock:
        _sessions[token] = time.time()
    return token


def _valid_session(token: str) -> bool:
    with _sessions_lock:
        created = _sessions.get(token)
    if created is None:
        return False
    if time.time() - created > _SESSION_TTL:
        with _sessions_lock:
            _sessions.pop(token, None)
        return False
    return True


def _parse_cookie(raw: str) -> dict:
    """Parse a Cookie header into a plain dict."""
    out = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out

STATE_PATH = "state.json"
_lb_cache = {"t": 0.0, "data": []}
_lb_lock = threading.Lock()


def _leaderboard(cfg, ttl=60):
    """Cached live leaderboard so the panel doesn't hammer the API per request."""
    now = time.time()
    with _lb_lock:
        if now - _lb_cache["t"] < ttl and _lb_cache["data"]:
            return _lb_cache["data"]
    try:
        rows = pm_data.top_traders(cfg.top_n, cfg.leaderboard_category, cfg.leaderboard_metric)
        for i, r in enumerate(rows):
            r["rank"] = i + 1
    except Exception:
        rows = _lb_cache["data"]
    with _lb_lock:
        _lb_cache["t"] = now
        _lb_cache["data"] = rows
    return rows


def _read_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def build_state(cfg):
    s = _read_state()
    lb = _leaderboard(cfg)
    name_by_wallet = {r["wallet"]: r["user_name"] for r in lb}

    base = cfg.account_size
    uptime = int(time.time() - _START)
    if not s:
        return {"live": False, "account_size": base, "leaderboard": lb,
                "positions": [], "closed": [], "history": [], "per_trader": [],
                "activity": [], "updated": time.time(), "uptime": uptime,
                "kpis": {"equity": base, "cash": base, "open_notional": 0,
                         "unrealized": 0, "realized": 0, "open_positions": 0,
                         "closed_trades": 0, "win_rate": 0, "profit_factor": 0,
                         "max_dd": 0, "winners": 0, "losers": 0, "ret_pct": 0}}

    # ---- open positions + per-trader rollup ----
    positions, by_trader = [], defaultdict(lambda: {"n": 0, "value": 0.0, "upnl": 0.0, "realized": 0.0})
    open_notional = unrealized = 0.0
    winners = losers = 0
    for p in s.get("positions", {}).values():
        cur = p["cur_price"] if p.get("cur_price", 0) > 0 else p["entry"]
        val = p["shares"] * cur
        upnl = (cur - p["entry"]) * p["shares"]
        open_notional += val
        unrealized += upnl
        winners += upnl > 0
        losers += upnl < 0
        name = name_by_wallet.get(p["wallet"], p.get("user_name", p["wallet"][:8]))
        t = by_trader[name]
        t["n"] += 1; t["value"] += val; t["upnl"] += upnl
        positions.append({
            "trader": name, "title": p.get("title", ""), "outcome": p.get("outcome", ""),
            "shares": p["shares"], "entry": p["entry"], "cur": cur, "value": val,
            "upnl": upnl, "upnl_pct": (cur / p["entry"] - 1.0) * 100 if p["entry"] else 0.0,
        })
    positions.sort(key=lambda x: x["upnl"], reverse=True)

    # ---- closed-trade stats + activity feed ----
    closed_all = s.get("closed", [])
    wins = [c for c in closed_all if c["pnl"] > 0]
    losses = [c for c in closed_all if c["pnl"] <= 0]
    win_rate = len(wins) / len(closed_all) if closed_all else 0.0
    gross_win = sum(c["pnl"] for c in wins)
    gross_loss = abs(sum(c["pnl"] for c in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (gross_win and 99.9)
    activity = []
    for c in reversed(closed_all[-25:]):
        nm = name_by_wallet.get(c.get("wallet", ""), c.get("wallet", "")[:8])
        by_trader[nm]["realized"] += c["pnl"]
        activity.append({"reason": c.get("reason", ""), "pnl": c["pnl"],
                         "title": c.get("title", ""), "trader": nm,
                         "exit": c.get("exit", 0)})

    # ---- equity trail + drawdown ----
    history = s.get("history", [])
    peak, mdd = -1e9, 0.0
    for h in history:
        peak = max(peak, h["equity"])
        if peak > 0:
            mdd = min(mdd, h["equity"] / peak - 1.0)

    cash = s.get("cash", base)
    realized = s.get("realized_pnl", 0.0)
    equity = cash + open_notional
    total = realized + unrealized
    per_trader = sorted(
        ({"trader": k, **v, "pnl": v["upnl"] + v["realized"]} for k, v in by_trader.items()),
        key=lambda x: x["pnl"], reverse=True)

    return {
        "live": True, "account_size": base, "leaderboard": lb, "updated": time.time(),
        "uptime": uptime, "positions": positions, "per_trader": per_trader,
        "closed": list(reversed(closed_all))[:40], "activity": activity,
        "history": history[-400:],
        "kpis": {
            "equity": equity, "cash": cash, "open_notional": open_notional,
            "unrealized": unrealized, "realized": realized, "total": total,
            "ret_pct": total / base * 100 if base else 0.0,
            "open_positions": len(positions), "closed_trades": len(closed_all),
            "win_rate": win_rate, "profit_factor": profit_factor or 0.0,
            "max_dd": mdd * 100, "winners": winners, "losers": losers,
            "best": positions[0]["upnl"] if positions else 0.0,
            "worst": positions[-1]["upnl"] if positions else 0.0,
        },
    }


def export_state(cfg):
    """Full, uncapped trade history for reports: every open + every closed trade."""
    bs = build_state(cfg)
    s = _read_state() or {}
    name_by_wallet = {r["wallet"]: r["user_name"] for r in bs.get("leaderboard", [])}
    closed = []
    for c in s.get("closed", []):
        closed.append({
            "trader": name_by_wallet.get(c.get("wallet", ""), c.get("wallet", "")[:10]),
            "title": c.get("title", ""), "reason": c.get("reason", ""),
            "entry": c.get("entry", 0.0), "exit": c.get("exit", 0.0),
            "shares": c.get("shares", 0.0), "pnl": c.get("pnl", 0.0),
        })
    return {
        "account_size": bs["account_size"], "kpis": bs["kpis"],
        "uptime": bs.get("uptime"), "open": bs["positions"], "closed": closed,
    }


class Handler(BaseHTTPRequestHandler):
    cfg = Config()

    def log_message(self, *a):
        pass  # quiet

    # ---- helpers ---------------------------------------------------------

    def _authenticated(self) -> bool:
        raw = self.headers.get("Cookie", "")
        cookies = _parse_cookie(raw)
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

    def _redirect(self, location: str, extra_headers=()):
        self.send_response(302)
        self.send_header("Location", location)
        for k, v in extra_headers:
            self.send_header(k, v)
        self.end_headers()

    def _require_auth(self) -> bool:
        """Return True if the request is authenticated; otherwise redirect and return False."""
        if self._authenticated():
            return True
        self._redirect("/login")
        return False

    # ---- GET -------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/login":
            self._send(LOGIN_PAGE, "text/html; charset=utf-8")
        elif path.startswith("/api/state"):
            if not self._authenticated():
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthenticated"}')
            else:
                self._send(json.dumps(build_state(self.cfg)))
        elif path.startswith("/api/export"):
            if not self._authenticated():
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthenticated"}')
            else:
                self._send(json.dumps(export_state(self.cfg)))
        elif path == "/" or path.startswith("/index"):
            if self._require_auth():
                self._send(PAGE, "text/html; charset=utf-8")
        # ---- PWA assets: public (non-sensitive) so install works on the login page ----
        elif path.startswith("/manifest"):
            self._send(MANIFEST, "application/manifest+json")
        elif path.startswith("/sw.js"):
            self._send(SW, "application/javascript")
        elif path.startswith("/icon.svg"):
            self._send(ICON, "image/svg+xml")
        else:
            self.send_response(404)
            self.end_headers()

    # ---- POST ------------------------------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            params = parse_qs(body)
            submitted = params.get("password", [""])[0]
            if submitted == _PASSWORD:
                token = _new_session()
                cookie = (
                    f"session={token}; Path=/; HttpOnly; SameSite=Lax; "
                    f"Max-Age={_SESSION_TTL}"
                )
                self._redirect("/", extra_headers=[("Set-Cookie", cookie)])
            else:
                self._send(
                    LOGIN_PAGE.replace("<!--ERROR-->",
                        '<p class="err">Incorrect password. Try again.</p>'),
                    "text/html; charset=utf-8",
                )
        else:
            self.send_response(404)
            self.end_headers()


LOGIN_PAGE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>PM COPY-TRADER // LOGIN</title>
  <link rel="icon" href="https://logodix.com/logo/606516.jpg" type="image/jpeg">
  <style>
    :root{--bg:#000;--amber:#ffae00;--dim:#6a6a52;--txt:#d7d0b0;--line:#332b12;--red:#ff3b3b;}
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:var(--bg);color:var(--txt);
         font:13px/1.5 "SF Mono",Menlo,Consolas,"Courier New",monospace;
         display:flex;align-items:center;justify-content:center;min-height:100vh;}
    .scan{position:fixed;inset:0;pointer-events:none;z-index:50;opacity:.35;
          background:repeating-linear-gradient(0deg,rgba(0,0,0,0) 0,rgba(0,0,0,0) 2px,rgba(0,0,0,.25) 3px);}
    .box{border:1px solid var(--line);padding:36px 40px;width:100%;max-width:360px;background:#0a0a0a;}
    .logo{color:var(--amber);font-weight:700;font-size:15px;letter-spacing:1px;margin-bottom:6px;}
    .sub{color:var(--dim);font-size:11px;margin-bottom:28px;letter-spacing:.5px;}
    label{display:block;color:var(--dim);font-size:10px;text-transform:uppercase;
          letter-spacing:.6px;margin-bottom:6px;}
    input[type=password]{width:100%;background:#000;border:1px solid var(--line);
          color:var(--txt);padding:9px 10px;font:13px/1 "SF Mono",Menlo,monospace;
          outline:none;margin-bottom:18px;}
    input[type=password]:focus{border-color:var(--amber);}
    button{width:100%;background:var(--amber);color:#000;border:none;padding:10px;
           font:700 13px/1 "SF Mono",Menlo,monospace;letter-spacing:.5px;cursor:pointer;}
    button:hover{opacity:.85;}
    .err{color:var(--red);font-size:11px;margin-bottom:14px;}
    .cursor{animation:blink 1s steps(2,start) infinite}
    @keyframes blink{50%{opacity:0}}
  </style>
</head>
<body>
<div class="scan"></div>
<div class="box">
  <div class="logo">PM COPY-TRADER<span class="cursor">_</span></div>
  <div class="sub">TERMINAL ACCESS &mdash; AUTHENTICATION REQUIRED</div>
  <!--ERROR-->
  <form method="POST" action="/login">
    <label for="pw">Password</label>
    <input type="password" id="pw" name="password" autofocus autocomplete="current-password">
    <button type="submit">ENTER &rarr;</button>
  </form>
</div>
</body>
</html>"""

# ---- PWA assets (installable phone app: Add to Home Screen) ----
MANIFEST = json.dumps({
    "name": "PM Copy-Trader Terminal", "short_name": "CopyTrader",
    "description": "Polymarket copy-trading paper terminal",
    "start_url": "/", "display": "standalone", "orientation": "any",
    "background_color": "#000000", "theme_color": "#ffae00",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml",
               "purpose": "any maskable"}],
})

SW = r"""const C='ct-v3';
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(['/','/icon.svg','/manifest.webmanifest'])));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);
  if(u.pathname.startsWith('/api/'))return;          // live data always hits network
  e.respondWith(fetch(e.request).then(r=>{const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp));return r;}).catch(()=>caches.match(e.request)));});
"""

ICON = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="96" fill="#0a0a0a"/>
<rect x="28" y="28" width="456" height="456" rx="72" fill="none" stroke="#ffae00" stroke-width="14"/>
<polyline points="80,330 150,300 200,330 260,250 320,280 380,170 432,150" fill="none" stroke="#19ff7a" stroke-width="16" stroke-linejoin="round" stroke-linecap="round"/>
<text x="256" y="430" font-family="monospace" font-size="120" font-weight="bold" fill="#ffae00" text-anchor="middle">PM</text>
</svg>
"""

PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>PM COPY-TRADER // TERMINAL</title>
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#ffae00">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="CopyTrader">
<link rel="apple-touch-icon" href="/icon.svg">
<link rel="icon" href="/icon.svg">
<link rel="icon" href="https://logodix.com/logo/606516.jpg" type="image/jpeg">
<style>
  :root{--bg:#000;--panel:#0a0a0a;--panel2:#0d0d07;--amber:#ffae00;--amber2:#7a5400;
        --grn:#19ff7a;--red:#ff3b3b;--dim:#6a6a52;--txt:#d7d0b0;--line:#332b12;--cyan:#36d0e0;}
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--bg);color:var(--txt);overscroll-behavior:none;overflow-x:hidden;width:100%;
       font:12px/1.35 "SF Mono",Menlo,Consolas,"Courier New",monospace;}
  /* CRT scanline overlay (fun) */
  .scan{position:fixed;inset:0;pointer-events:none;z-index:50;opacity:.35;
        background:repeating-linear-gradient(0deg,rgba(0,0,0,0) 0,rgba(0,0,0,0) 2px,rgba(0,0,0,.25) 3px);}
  .glow{text-shadow:0 0 6px rgba(255,174,0,.55)}
  /* top bar */
  .bar{display:flex;align-items:center;gap:12px;background:#140e00;flex-wrap:wrap;
       border-bottom:2px solid var(--amber);padding:6px 10px;color:var(--amber);font-weight:700;letter-spacing:.5px}
  .bar .tag{background:var(--amber);color:#000;padding:1px 6px;border-radius:2px}
  .bar .paper{color:var(--red);border:1px solid var(--red);padding:0 6px;border-radius:2px;font-size:11px}
  .bar .sp{flex:1}
  .cursor{animation:blink 1s steps(2,start) infinite}@keyframes blink{50%{opacity:0}}
  .led{animation:pulse 1.5s ease-in-out infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  /* ticker tape */
  .ticker{background:#0b0800;border-bottom:1px solid var(--line);overflow:hidden;white-space:nowrap;padding:3px 0}
  #tape{display:inline-block;will-change:transform;animation:scroll 60s linear infinite}
  #tape:hover{animation-play-state:paused}
  @keyframes scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}
  .tk{padding:0 16px;color:var(--dim)}
  /* kpis */
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line)}
  .kpi{background:var(--panel);padding:6px 9px}
  .kpi .k{color:var(--dim);font-size:9.5px;text-transform:uppercase;letter-spacing:.6px}
  .kpi .v{font-size:17px;font-weight:700;margin-top:2px;white-space:nowrap}
  /* layout */
  .grid{display:grid;grid-template-columns:1.45fr 1fr;gap:1px;background:var(--line);min-width:0}
  .col{display:flex;flex-direction:column;gap:1px;background:var(--line);min-width:0}
  .panel{background:var(--panel);min-width:0;overflow:hidden}
  .ph{color:var(--amber);background:#100b00;padding:4px 9px;font-weight:700;letter-spacing:1px;
      border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
  .ph .c{color:var(--dim);font-weight:400;font-size:10px}
  .tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
  table{width:100%;border-collapse:collapse}
  th{color:var(--dim);text-align:right;font-weight:400;font-size:9.5px;text-transform:uppercase;
     padding:3px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
  th.l,td.l{text-align:left}
  td{padding:3px 9px;border-bottom:1px solid #161204;text-align:right;white-space:nowrap}
  tr:hover td{background:#161000}
  .pos{color:var(--grn)}.neg{color:var(--red)}.am{color:var(--amber)}.mut{color:var(--dim)}.cy{color:var(--cyan)}
  .truncate{max-width:230px;overflow:hidden;text-overflow:ellipsis}
  .chartwrap{padding:8px 10px}
  svg{width:100%;height:160px;display:block}
  /* health rows */
  .kv{display:grid;grid-template-columns:1fr auto;gap:2px 8px;padding:6px 9px}
  .kv div{padding:1px 0}.kv .lbl{color:var(--dim)}
  .barrow{display:grid;grid-template-columns:90px 1fr 64px;align-items:center;gap:8px;padding:3px 9px}
  .barrow .nm{color:var(--amber);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .bartrack{height:9px;background:#1a1405;border:1px solid var(--line);position:relative}
  .barfill{height:100%;position:absolute;top:0}
  .act{padding:3px 9px;border-bottom:1px solid #161204;display:flex;gap:8px;align-items:baseline}
  .act .rsn{color:var(--dim);min-width:78px}
  .foot{background:#0c0900;border-top:1px solid var(--line);color:var(--dim);padding:4px 10px;
        font-size:11px;display:flex;gap:16px;flex-wrap:wrap}
  .empty{color:var(--dim);padding:10px 9px}
  /* responsive: phones/tablets */
  @media(max-width:860px){
    .grid{grid-template-columns:1fr}
    .kpis{grid-template-columns:repeat(3,1fr)}
    .kpi .v{font-size:15px}.kpi{padding:5px 8px}
    .truncate{max-width:42vw}
    .hide-sm{display:none}
    th,td{padding:3px 7px}
    .barrow{grid-template-columns:72px 1fr 56px;gap:6px}
    .act{gap:6px}.act .rsn{min-width:56px}
    .bar{gap:8px;font-size:11px}
    svg{height:140px}
  }
  @media(max-width:430px){
    .kpis{grid-template-columns:repeat(2,1fr)}
    .kpi .v{font-size:14px}
    .truncate{max-width:48vw}
  }
</style></head><body>
<div class="scan"></div>
<div class="bar">
  <span class="tag">PM</span><span class="glow">POLYMARKET COPY-TRADER<span class="cursor">_</span></span>
  <span class="paper">PAPER &middot; NO LIVE ORDERS</span>
  <span class="sp"></span>
  <span id="conn" class="am led">&#9679; LIVE</span>
  <span id="up" class="mut"></span>
  <span id="clock" class="mut"></span>
</div>

<div class="ticker"><div id="tape"></div></div>

<div class="kpis" id="kpis"></div>

<div class="grid">
  <div class="col">
    <div class="panel">
      <div class="ph">EQUITY CURVE <span class="c" id="eqsub"></span></div>
      <div class="chartwrap"><svg id="chart" viewBox="0 0 600 160" preserveAspectRatio="none"></svg></div>
    </div>
    <div class="panel">
      <div class="ph">OPEN POSITIONS <span class="c" id="poscount"></span></div>
      <div class="tw"><table><thead><tr>
        <th class="l">TRADER</th><th class="l">MARKET</th><th class="hide-sm">OUT</th>
        <th class="hide-sm">SH</th><th class="hide-sm">ENTRY</th><th>MARK</th><th>VALUE</th><th>uPNL</th><th>%</th>
      </tr></thead><tbody id="positions"></tbody></table></div>
    </div>
    <div class="panel">
      <div class="ph">ACTIVITY &middot; RECENT EXITS <span class="c" id="actcount"></span></div>
      <div id="activity"></div>
    </div>
  </div>

  <div class="col">
    <div class="panel">
      <div class="ph">HEALTH &middot; STATS</div>
      <div class="kv" id="health"></div>
    </div>
    <div class="panel">
      <div class="ph">P&amp;L BY TRADER <span class="c">unreal + real</span></div>
      <div id="pertrader"></div>
    </div>
    <div class="panel">
      <div class="ph">SMART MONEY &middot; TOP TRADERS <span class="c">PnL</span></div>
      <div class="tw"><table><thead><tr>
        <th class="l">#</th><th class="l">TRADER</th><th>PNL</th><th class="hide-sm">VOL</th>
      </tr></thead><tbody id="leaders"></tbody></table></div>
    </div>
    <div class="panel">
      <div class="ph">BLOTTER &middot; CLOSED <span class="c" id="blcount"></span></div>
      <div class="tw"><table><thead><tr>
        <th class="l">MARKET</th><th>REASON</th><th class="hide-sm">EXIT</th><th>PNL</th>
      </tr></thead><tbody id="closed"></tbody></table></div>
    </div>
  </div>
</div>

<div class="foot">
  <span id="status">CONNECTING&hellip;</span>
  <span class="sp" style="flex:1"></span>
  <span>SRC polymarket data-api / clob</span>
  <span id="updated"></span>
</div>

<script>
const $=s=>document.querySelector(s);
const m0=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString(undefined,{maximumFractionDigits:0});
const m2=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const big=n=>{const a=Math.abs(n);if(a>=1e6)return(n/1e6).toFixed(2)+'M';if(a>=1e3)return(n/1e3).toFixed(1)+'K';return n.toFixed(0);};
const sgn=n=>n>0?'pos':(n<0?'neg':'mut');
const arr=n=>n>0?'▲':(n<0?'▼':'·');
const esc=s=>(s||'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
const dur=s=>{s=s|0;const h=(s/3600)|0,m=((s%3600)/60)|0;return h?`${h}h${m}m`:`${m}m`;};
function kpi(k,v,c){return `<div class="kpi"><div class="k">${k}</div><div class="v ${c||''}">${v}</div></div>`;}

function render(d){
  const k=d.kpis, base=d.account_size, tot=(k.total!==undefined?k.total:k.realized+k.unrealized);
  $('#kpis').innerHTML=[
    kpi('Equity',m2(k.equity),'am glow'),
    kpi('Total P&L',`${arr(tot)} ${m2(tot)}`,sgn(tot)),
    kpi('Return',(k.ret_pct||0).toFixed(2)+'%',sgn(tot)),
    kpi('Win Rate',((k.win_rate||0)*100).toFixed(0)+'%',(k.win_rate>=0.5?'pos':'neg')),
    kpi('Profit Factor',(k.profit_factor||0).toFixed(2),(k.profit_factor>=1?'pos':'neg')),
    kpi('Max DD',(k.max_dd||0).toFixed(2)+'%','neg'),
    kpi('Realized',m2(k.realized),sgn(k.realized)),
    kpi('Unrealized',m2(k.unrealized),sgn(k.unrealized)),
    kpi('Exposure',m0(k.open_notional),''),
    kpi('Cash',m0(k.cash),'mut'),
    kpi('Open',k.open_positions+'','cy'),
    kpi('Closed',k.closed_trades+'','mut'),
  ].join('');

  // ticker tape
  const items=[];
  (d.positions||[]).slice(0,16).forEach(p=>items.push(
    `<span class="tk"><span class="am">${esc(p.trader)}</span> ${esc(p.title).slice(0,22)} `+
    `<span class="${sgn(p.upnl)}">${arr(p.upnl)} ${m2(p.upnl)}</span></span>`));
  (d.activity||[]).slice(0,8).forEach(a=>items.push(
    `<span class="tk">${esc(a.reason)} ${esc(a.title).slice(0,18)} <span class="${sgn(a.pnl)}">${m2(a.pnl)}</span></span>`));
  const tape=items.join('<span class="tk mut">&bull;</span>')||'<span class="tk mut">awaiting data&hellip;</span>';
  $('#tape').innerHTML=tape+'<span class="tk mut">&bull;</span>'+tape;

  // open positions
  $('#poscount').textContent=k.open_positions+' · '+m0(k.open_notional)+' · '+(k.winners||0)+'W/'+(k.losers||0)+'L';
  const pb=$('#positions');
  if(!(d.positions||[]).length){pb.innerHTML='<tr><td colspan="9" class="empty">No open copies yet.</td></tr>';}
  else pb.innerHTML=d.positions.map(p=>`<tr>
     <td class="l am">${esc(p.trader)}</td>
     <td class="l truncate" title="${esc(p.title)}">${esc(p.title)}</td>
     <td class="hide-sm mut">${esc(p.outcome)}</td>
     <td class="hide-sm">${p.shares.toLocaleString(undefined,{maximumFractionDigits:0})}</td>
     <td class="hide-sm">${p.entry.toFixed(3)}</td><td>${p.cur.toFixed(3)}</td>
     <td>${m0(p.value)}</td>
     <td class="${sgn(p.upnl)}">${m2(p.upnl)}</td>
     <td class="${sgn(p.upnl)}">${arr(p.upnl)}${Math.abs(p.upnl_pct).toFixed(1)}</td></tr>`).join('');

  // health
  $('#health').innerHTML=[
    ['Winners / Losers (open)',`<span class="pos">${k.winners||0}</span> / <span class="neg">${k.losers||0}</span>`],
    ['Best open',`<span class="pos">${m2(k.best||0)}</span>`],
    ['Worst open',`<span class="neg">${m2(k.worst||0)}</span>`],
    ['Profit factor',(k.profit_factor||0).toFixed(2)],
    ['Win rate',((k.win_rate||0)*100).toFixed(0)+'%'],
    ['Max drawdown',`<span class="neg">${(k.max_dd||0).toFixed(2)}%</span>`],
    ['Deployed',((k.open_notional/base)*100).toFixed(0)+'%'],
    ['Equity points',(d.history||[]).length],
    ['Uptime',dur(d.uptime||0)],
  ].map(r=>`<div class="lbl">${r[0]}</div><div>${r[1]}</div>`).join('');

  // per-trader bars
  const pt=d.per_trader||[]; const mx=Math.max(1,...pt.map(t=>Math.abs(t.pnl)));
  $('#pertrader').innerHTML=pt.length?pt.map(t=>{
    const w=Math.min(50,Math.abs(t.pnl)/mx*50), pos=t.pnl>=0;
    const left=pos?'50%':(50-w)+'%', col=pos?'var(--grn)':'var(--red)';
    return `<div class="barrow"><div class="nm">${esc(t.trader)}</div>
      <div class="bartrack"><div class="barfill" style="left:${left};width:${w}%;background:${col}"></div>
      <div style="position:absolute;left:50%;top:-1px;bottom:-1px;border-left:1px solid var(--dim)"></div></div>
      <div class="${sgn(t.pnl)}" style="text-align:right">${m2(t.pnl)} <span class="mut">(${t.n})</span></div></div>`;
  }).join(''):'<div class="empty">No positions.</div>';

  // leaders
  $('#leaders').innerHTML=(d.leaderboard||[]).map(r=>`<tr>
     <td class="l mut">${r.rank}</td><td class="l am">${esc(r.user_name)}</td>
     <td class="pos">$${big(r.pnl)}</td><td class="hide-sm mut">$${big(r.vol)}</td></tr>`).join('');

  // activity
  $('#actcount').textContent=(d.activity||[]).length+' shown';
  const af=$('#activity');
  if(!(d.activity||[]).length){af.innerHTML='<div class="empty">No closed trades yet.</div>';}
  else af.innerHTML=d.activity.map(a=>`<div class="act">
     <span class="rsn">${esc(a.reason)}</span>
     <span class="am" style="min-width:74px">${esc(a.trader)}</span>
     <span class="truncate mut" title="${esc(a.title)}">${esc(a.title)}</span>
     <span class="sp" style="flex:1"></span>
     <span class="${sgn(a.pnl)}">${arr(a.pnl)} ${m2(a.pnl)}</span></div>`).join('');

  // blotter
  $('#blcount').textContent=k.closed_trades+' filled';
  const cb=$('#closed');
  if(!(d.closed||[]).length){cb.innerHTML='<tr><td colspan="4" class="empty">No closed trades yet.</td></tr>';}
  else cb.innerHTML=d.closed.map(c=>`<tr>
     <td class="l truncate" title="${esc(c.title)}">${esc(c.title)}</td>
     <td class="mut">${esc(c.reason)}</td><td class="hide-sm">${(c.exit||0).toFixed(3)}</td>
     <td class="${sgn(c.pnl)}">${m2(c.pnl)}</td></tr>`).join('');

  drawChart(d.history||[],base);
  $('#eqsub').textContent=(d.history||[]).length?(d.history.length+' pts'):'awaiting data';
  $('#status').innerHTML=d.live?'&#9679; ENGINE STATE LOADED':'&#9675; WAITING FOR ENGINE';
  $('#up').textContent='UP '+dur(d.uptime||0);
  $('#updated').textContent='UPD '+new Date(d.updated*1000).toLocaleTimeString();
}

function drawChart(h,base){
  const svg=$('#chart'),W=600,H=160,pad=4;
  if(h.length<2){svg.innerHTML=`<line x1="0" y1="${H/2}" x2="${W}" y2="${H/2}" stroke="#332b12"/>`;return;}
  const eq=h.map(p=>p.equity);let lo=Math.min(...eq,base),hi=Math.max(...eq,base);
  if(hi-lo<1e-6){hi+=1;lo-=1;}
  const x=i=>pad+i*(W-2*pad)/(h.length-1), y=v=>H-pad-(v-lo)/(hi-lo)*(H-2*pad);
  const pts=eq.map((v,i)=>x(i).toFixed(1)+','+y(v).toFixed(1)).join(' ');
  const last=eq[eq.length-1],up=last>=base,col=up?'#19ff7a':'#ff3b3b',by=y(base).toFixed(1);
  svg.innerHTML=`
    <polygon points="${pad},${H-pad} ${pts} ${(W-pad)},${H-pad}" fill="${col}" opacity="0.08"/>
    <line x1="0" y1="${by}" x2="${W}" y2="${by}" stroke="#4a3d10" stroke-dasharray="3 3"/>
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5"/>
    <circle cx="${x(eq.length-1)}" cy="${y(last)}" r="2.5" fill="${col}"/>
    <text x="6" y="13" fill="#6a6a52" font-size="10">$${hi.toLocaleString(undefined,{maximumFractionDigits:0})}</text>
    <text x="6" y="${H-4}" fill="#6a6a52" font-size="10">$${lo.toLocaleString(undefined,{maximumFractionDigits:0})}</text>`;
}

async function tick(){
  try{const r=await fetch('/api/state');
    if(r.status===401||r.status===403){location.href='/login';return;}  // session died -> log in again
    const d=await r.json();render(d);
    $('#conn').textContent='● LIVE';$('#conn').className='am led';
  }catch(e){$('#conn').textContent='● DISCONNECTED';$('#conn').className='neg';}
}
setInterval(()=>{$('#clock').textContent=new Date().toLocaleTimeString();},1000);
tick();setInterval(tick,4000);
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
</script></body></html>"""


def main():
    global STATE_PATH
    port = 8787
    host = "127.0.0.1"            # localhost only by default
    argv = sys.argv[1:]
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--state" in argv:
        STATE_PATH = argv[argv.index("--state") + 1]
    if "--host" in argv:
        # e.g. --host 0.0.0.0 (all interfaces) or --host 100.x.y.z (Tailscale IP only)
        host = argv[argv.index("--host") + 1]
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"terminal up -> http://{host}:{port}   (state: {os.path.abspath(STATE_PATH)})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
