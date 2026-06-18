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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import pm_data
from .config import Config

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

    if not s:
        return {"live": False, "account_size": cfg.account_size,
                "leaderboard": lb, "positions": [], "closed": [],
                "history": [], "updated": time.time(),
                "kpis": {"equity": cfg.account_size, "cash": cfg.account_size,
                         "open_notional": 0, "unrealized": 0, "realized": 0,
                         "open_positions": 0, "closed_trades": 0}}

    positions = []
    open_notional = unrealized = 0.0
    for p in s.get("positions", {}).values():
        cur = p["cur_price"] if p.get("cur_price", 0) > 0 else p["entry"]
        val = p["shares"] * cur
        upnl = (cur - p["entry"]) * p["shares"]
        open_notional += val
        unrealized += upnl
        positions.append({
            "trader": name_by_wallet.get(p["wallet"], p.get("user_name", p["wallet"][:8])),
            "title": p.get("title", ""), "outcome": p.get("outcome", ""),
            "shares": p["shares"], "entry": p["entry"], "cur": cur,
            "value": val, "upnl": upnl,
            "upnl_pct": (cur / p["entry"] - 1.0) * 100 if p["entry"] else 0.0,
        })
    positions.sort(key=lambda x: x["value"], reverse=True)

    cash = s.get("cash", cfg.account_size)
    realized = s.get("realized_pnl", 0.0)
    closed = list(reversed(s.get("closed", [])))[:40]
    return {
        "live": True, "account_size": cfg.account_size, "leaderboard": lb,
        "positions": positions, "closed": closed,
        "history": s.get("history", [])[-400:], "updated": time.time(),
        "kpis": {
            "equity": cash + open_notional, "cash": cash,
            "open_notional": open_notional, "unrealized": unrealized,
            "realized": realized, "open_positions": len(positions),
            "closed_trades": len(s.get("closed", [])),
        },
    }


class Handler(BaseHTTPRequestHandler):
    cfg = Config()

    def log_message(self, *a):
        pass  # quiet

    def _send(self, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._send(json.dumps(build_state(self.cfg)))
        elif self.path == "/" or self.path.startswith("/index"):
            self._send(PAGE, "text/html; charset=utf-8")
        else:
            self.send_response(404)
            self.end_headers()


PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>PM COPY-TRADER // TERMINAL</title>
<style>
  :root{--bg:#000;--panel:#0a0a0a;--amber:#ffae00;--amber2:#7a5400;--grn:#19ff7a;
        --red:#ff3b3b;--dim:#5c5c4a;--txt:#d7d0b0;--line:#332b12;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
       font:12px/1.35 "SF Mono",Menlo,Consolas,"Courier New",monospace;}
  .bar{display:flex;align-items:center;gap:14px;background:#140e00;
       border-bottom:2px solid var(--amber);padding:5px 10px;color:var(--amber);
       font-weight:700;letter-spacing:.5px;}
  .bar .tag{background:var(--amber);color:#000;padding:1px 6px;border-radius:2px}
  .bar .paper{color:var(--red);border:1px solid var(--red);padding:0 6px;border-radius:2px;font-size:11px}
  .bar .spacer{flex:1}
  .kpis{display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:var(--line)}
  .kpi{background:var(--panel);padding:7px 10px}
  .kpi .k{color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.6px}
  .kpi .v{font-size:18px;font-weight:700;margin-top:2px}
  .grid{display:grid;grid-template-columns:1.35fr 1fr;gap:1px;background:var(--line)}
  .col{display:flex;flex-direction:column;gap:1px;background:var(--line)}
  .panel{background:var(--panel);border-top:1px solid var(--line)}
  .ph{color:var(--amber);background:#100b00;padding:4px 9px;font-weight:700;
      letter-spacing:1px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between}
  .ph .c{color:var(--dim);font-weight:400}
  table{width:100%;border-collapse:collapse}
  th{color:var(--dim);text-align:right;font-weight:400;font-size:10px;
     text-transform:uppercase;padding:3px 9px;border-bottom:1px solid var(--line)}
  th.l,td.l{text-align:left}
  td{padding:3px 9px;border-bottom:1px solid #161204;text-align:right;white-space:nowrap}
  tr:hover td{background:#161000}
  .pos{color:var(--grn)} .neg{color:var(--red)} .am{color:var(--amber)}
  .mut{color:var(--dim)}
  .truncate{max-width:230px;overflow:hidden;text-overflow:ellipsis}
  .chartwrap{padding:8px 10px}
  svg{width:100%;height:150px;display:block}
  .foot{background:#0c0900;border-top:1px solid var(--line);color:var(--dim);
        padding:3px 10px;font-size:11px;display:flex;gap:18px}
  .blink{animation:b 1.4s steps(2,start) infinite}@keyframes b{50%{opacity:.25}}
  .empty{color:var(--dim);padding:10px 9px}
</style></head><body>
<div class="bar">
  <span class="tag">PM</span> POLYMARKET COPY-TRADER
  <span class="paper">PAPER · NO LIVE ORDERS</span>
  <span class="spacer"></span>
  <span id="conn" class="am blink">● LIVE</span>
  <span id="clock" class="mut"></span>
</div>

<div class="kpis" id="kpis"></div>

<div class="grid">
  <div class="col">
    <div class="panel">
      <div class="ph">EQUITY CURVE <span class="c" id="eqsub"></span></div>
      <div class="chartwrap"><svg id="chart" viewBox="0 0 600 150" preserveAspectRatio="none"></svg></div>
    </div>
    <div class="panel">
      <div class="ph">OPEN POSITIONS <span class="c" id="poscount"></span></div>
      <table><thead><tr>
        <th class="l">TRADER</th><th class="l">MARKET</th><th>OUT</th>
        <th>SHARES</th><th>ENTRY</th><th>MARK</th><th>VALUE</th><th>uPNL</th><th>%</th>
      </tr></thead><tbody id="positions"></tbody></table>
    </div>
  </div>
  <div class="col">
    <div class="panel">
      <div class="ph">SMART MONEY · TOP TRADERS <span class="c">PnL</span></div>
      <table><thead><tr>
        <th class="l">#</th><th class="l">TRADER</th><th>PNL</th><th>VOL</th>
      </tr></thead><tbody id="leaders"></tbody></table>
    </div>
    <div class="panel">
      <div class="ph">BLOTTER · CLOSED <span class="c" id="blcount"></span></div>
      <table><thead><tr>
        <th class="l">MARKET</th><th>REASON</th><th>EXIT</th><th>PNL</th>
      </tr></thead><tbody id="closed"></tbody></table>
    </div>
  </div>
</div>

<div class="foot">
  <span id="status">CONNECTING…</span>
  <span class="spacer" style="flex:1"></span>
  <span id="updated"></span>
</div>

<script>
const $=s=>document.querySelector(s);
const money=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString(undefined,{maximumFractionDigits:0});
const money2=n=>(n<0?'-$':'$')+Math.abs(n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const big=n=>{const a=Math.abs(n);if(a>=1e6)return (n/1e6).toFixed(2)+'M';if(a>=1e3)return (n/1e3).toFixed(1)+'K';return n.toFixed(0);};
const sgn=n=>n>0?'pos':(n<0?'neg':'mut');
const arrow=n=>n>0?'▲':(n<0?'▼':'·');

function kpi(k,v,cls){return `<div class="kpi"><div class="k">${k}</div><div class="v ${cls||''}">${v}</div></div>`;}

function render(d){
  const k=d.kpis, base=d.account_size, tot=k.realized+k.unrealized, totpct=base?tot/base*100:0;
  $('#kpis').innerHTML=[
    kpi('Equity', money2(k.equity), 'am'),
    kpi('Total P&L', `${arrow(tot)} ${money2(tot)}`, sgn(tot)),
    kpi('Return', totpct.toFixed(2)+'%', sgn(tot)),
    kpi('Unrealized', money2(k.unrealized), sgn(k.unrealized)),
    kpi('Realized', money2(k.realized), sgn(k.realized)),
    kpi('Exposure', money(k.open_notional), ''),
    kpi('Cash', money(k.cash), 'mut'),
  ].join('');

  $('#poscount').textContent=k.open_positions+' OPEN · '+money(k.open_notional);
  const pb=$('#positions');
  if(!d.positions.length){pb.innerHTML='<tr><td colspan="9" class="empty">No open copies yet — engine is baselining traders & waiting for them to trade.</td></tr>';}
  else pb.innerHTML=d.positions.map(p=>`<tr>
     <td class="l am">${p.trader}</td>
     <td class="l truncate" title="${p.title}">${p.title}</td>
     <td>${p.outcome}</td>
     <td>${p.shares.toLocaleString(undefined,{maximumFractionDigits:0})}</td>
     <td>${p.entry.toFixed(3)}</td><td>${p.cur.toFixed(3)}</td>
     <td>${money(p.value)}</td>
     <td class="${sgn(p.upnl)}">${money2(p.upnl)}</td>
     <td class="${sgn(p.upnl)}">${p.upnl_pct.toFixed(1)}</td></tr>`).join('');

  $('#leaders').innerHTML=d.leaderboard.map(r=>`<tr>
     <td class="l mut">${r.rank}</td><td class="l am">${r.user_name}</td>
     <td class="pos">$${big(r.pnl)}</td><td class="mut">$${big(r.vol)}</td></tr>`).join('');

  $('#blcount').textContent=k.closed_trades+' FILLED';
  const cb=$('#closed');
  if(!d.closed.length){cb.innerHTML='<tr><td colspan="4" class="empty">No closed trades yet.</td></tr>';}
  else cb.innerHTML=d.closed.map(c=>`<tr>
     <td class="l truncate" title="${c.title}">${c.title}</td>
     <td class="mut">${c.reason}</td><td>${(c.exit||0).toFixed(3)}</td>
     <td class="${sgn(c.pnl)}">${money2(c.pnl)}</td></tr>`).join('');

  drawChart(d.history, base);
  $('#eqsub').textContent=d.history.length?d.history.length+' pts':'awaiting data';
  $('#status').innerHTML=d.live?'● ENGINE STATE LOADED':'○ WAITING FOR ENGINE (run: python3 -m copytrader.run)';
  $('#updated').textContent='UPD '+new Date(d.updated*1000).toLocaleTimeString();
}

function drawChart(h, base){
  const svg=$('#chart'); const W=600,H=150,pad=4;
  if(h.length<2){svg.innerHTML=`<line x1="0" y1="${H/2}" x2="${W}" y2="${H/2}" stroke="#332b12"/>`;return;}
  const eq=h.map(p=>p.equity); let lo=Math.min(...eq,base), hi=Math.max(...eq,base);
  if(hi-lo<1e-6){hi+=1;lo-=1;}
  const x=i=>pad+i*(W-2*pad)/(h.length-1);
  const y=v=>H-pad-(v-lo)/(hi-lo)*(H-2*pad);
  const pts=eq.map((v,i)=>x(i).toFixed(1)+','+y(v).toFixed(1)).join(' ');
  const last=eq[eq.length-1], up=last>=base;
  const col=up?'#19ff7a':'#ff3b3b';
  const baseY=y(base).toFixed(1);
  const area=`${pad},${H-pad} ${pts} ${(W-pad)},${H-pad}`;
  svg.innerHTML=`
    <polygon points="${area}" fill="${col}" opacity="0.08"/>
    <line x1="0" y1="${baseY}" x2="${W}" y2="${baseY}" stroke="#4a3d10" stroke-dasharray="3 3"/>
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5"/>
    <text x="6" y="13" fill="#5c5c4a" font-size="10">$${hi.toLocaleString(undefined,{maximumFractionDigits:0})}</text>
    <text x="6" y="${H-4}" fill="#5c5c4a" font-size="10">$${lo.toLocaleString(undefined,{maximumFractionDigits:0})}</text>`;
}

async function tick(){
  try{
    const r=await fetch('/api/state'); const d=await r.json();
    render(d); $('#conn').textContent='● LIVE'; $('#conn').className='am blink';
  }catch(e){ $('#conn').textContent='● DISCONNECTED'; $('#conn').className='neg'; }
}
setInterval(()=>{$('#clock').textContent=new Date().toLocaleTimeString();},1000);
tick(); setInterval(tick,4000);
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
