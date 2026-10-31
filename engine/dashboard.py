# -*- coding: utf-8 -*-
"""训练台：记录训练过程的可视化面板（纯标准库，零依赖）。

为什么用本地网页而不是桌面窗口
    · 项目纪律是纯标准库、零第三方依赖 —— `http.server` 正好够
    · 图表用内联 SVG 画，不需要任何库
    · 浏览器里能刷新、能截图、能在手机上开（同一局域网）

面板上有什么（每一块都对应训练循环的一环）
    ┌ 训练进度 ── 跑了多少轮、输入从哪来、训练师开没开
    ├ 性格      ── 极性变量（带读数来源）／里程碑（当前 vs 历史最高）
    ├ 状态轨迹  ── 极性变量随轮次怎么走（画线，看得出在不在动）
    ├ 交流记录  ── 逐轮：他说什么 / 系统回什么 / 内部判定 / 训练师怎么评
    ├ 管理员队列 ── 事实层（可作依据）／意见层（只作线索）／提案，可批准或驳回
    └ 改动历史  ── 批准过什么（只追加，不删）

⚠️ 面板**不改任何东西**，除了记录你的批准/驳回决定。
   行为类改动仍要靠人（或我）动手，然后跑回归 —— 这是刻意的：
   一个能自动改系统的面板，就是一个能自动改坏系统的面板。
"""
from __future__ import annotations

import io
import json
import os
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TRAIN_DIR = os.path.join(_ROOT, "state", "train")
DEFAULT_PORT = 8791

POLARITY_SOURCE = {
    "wanting": "[D] 想要（Hz，静止带 3–5／爆发带 20–30）",
    "liking": "[D] 喜欢（当下分子）",
    "patience": "[D] 敏化增益的反面（失望累积越多越耐不住）",
    "structure": "[E] 结构预测误差（平衡化压力）",
    "tension": "[M] 张力（趋零是病态，不是健康）",
}


# ------------------------------------------------------------------ 数据

def _jsonl(p: str) -> list[dict]:
    out = []
    if not os.path.exists(p):
        return out
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:                      # noqa: BLE001
                pass
    return out


def _json(p: str, d=None):
    if not os.path.exists(p):
        return d
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except Exception:                              # noqa: BLE001
        return d


def collect() -> dict:
    """把面板要的一切收成一个 JSON。**只读，不写。**"""
    import admin as A
    from character import POLARITY_NAME, polarity_from_mech

    led = os.path.join(TRAIN_DIR, "ledger.jsonl")
    ev = os.path.join(TRAIN_DIR, "eval.jsonl")
    rows = [r for r in _jsonl(led) if not r.get("__ERA_BOUNDARY__") and not r.get("void")]
    evals = _jsonl(ev)
    prog = _json(prog_p := os.path.join(TRAIN_DIR, "progress.json"), {}) or {}
    ch = _json(os.path.join(TRAIN_DIR, "character.json"), {}) or {}
    q = _json(os.path.join(TRAIN_DIR, "review_queue.json"), {}) or {}
    dec = _jsonl(os.path.join(TRAIN_DIR, "decisions.jsonl"))

    # 极性轨迹：从每轮机制快照读（与 character.polarity_from_mech 同一来源，
    # 不另写一份公式 —— 两份公式迟早不一致，然后互相"验证"）
    traj = []
    for r in rows:
        m = r.get("mech")
        if not m:
            continue
        p = polarity_from_mech(m).to_dict()
        traj.append({"t": r.get("turn_id"), "w": p["wanting"], "l": p["liking"],
                     "p": p["patience"], "s": p["structure"], "tn": p["tension"]})

    # 逐轮记录：把训练师的评价按输入对齐
    jmap = {}
    for e in evals:
        jmap.setdefault(e.get("input", ""), []).append(e.get("tutor") or {})
    turns = []
    for i, r in enumerate(rows[-60:]):
        raw = (r.get("raw_input") or "")
        j = (jmap.get(raw) or [{}])[0] if jmap.get(raw) else {}
        turns.append({"turn": r.get("turn_id"), "topic": r.get("topic_id"),
                      "input": raw[:80], "output": (r.get("output") or "")[:200],
                      "behavior": r.get("behavior"), "markers": r.get("markers_fired") or [],
                      "channel": r.get("channel"), "era": r.get("era"),
                      "char_note": r.get("character_note"),
                      "notes": [n for n in (r.get("notes") or [])
                                if "退回" in n or "介入" in n or "分歧" in n][:3],
                      "judge": j.get("problem") if j else None,
                      "judge_why": (j.get("why") or "")[:60] if j else ""})

    ms = []
    for m in ch.get("milestones", []):
        ms.append({"text": m.get("text"), "current": m.get("current"),
                   "peak": m.get("evidence"), "era": m.get("era"),
                   "basis": m.get("basis") or {}})

    return {
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        "progress": prog,
        "counts": {"turns": len(rows), "evals": len(evals),
                   "sessions": prog.get("sessions", 0),
                   "rounds": prog.get("rounds", 0)},
        "polarity": ch.get("polarity") or {},
        "polarity_names": POLARITY_NAME,
        "polarity_source": POLARITY_SOURCE,
        "trajectory": traj,
        "milestones": ms,
        "turns": turns,
        "queue": {"facts": q.get("facts", []), "opinions": q.get("opinions", []),
                  "proposals": q.get("proposals", []),
                  "generated": q.get("generated")},
        "decisions": dec[-20:],
        "min_turns": A.MIN_TURNS,
        "has_data": bool(rows),
    }


# ------------------------------------------------------------------ 页面

PAGE = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>训练台 · 自我的发展</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0f1115;--fg:#e6e6e6;--dim:#8a9099;--card:#171a21;--line:#252a33;
--ok:#3fb950;--warn:#d29922;--bad:#f85149;--acc:#58a6ff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;
justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}
h1{font-size:17px;margin:0;font-weight:600}
h2{font-size:14px;margin:0 0 10px;color:var(--acc);font-weight:600}
.sub{color:var(--dim);font-size:12px}
main{padding:18px 22px;display:grid;gap:16px;
grid-template-columns:repeat(auto-fit,minmax(360px,1fr));align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.full{grid-column:1/-1}
.kpi{display:flex;gap:22px;flex-wrap:wrap}
.kpi div{min-width:76px}
.kpi b{display:block;font-size:22px;font-weight:600}
.kpi span{color:var(--dim);font-size:12px}
.bar{height:11px;background:#22262e;border-radius:6px;overflow:hidden;flex:1}
.bar>i{display:block;height:100%}
.row{display:flex;align-items:center;gap:10px;margin:7px 0}
.row .nm{width:74px;color:var(--dim);font-size:12px}
.row .vl{width:44px;text-align:right;font-variant-numeric:tabular-nums}
.warnbox{background:#1d1a10;border:1px solid #4a3a12;border-radius:8px;
padding:9px 11px;font-size:12px;color:#e8d9a8;margin-top:8px}
.turn{border-top:1px solid var(--line);padding:9px 0}
.turn .i{color:#c9d1d9}.turn .o{color:#9fb6cf}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;
background:#22262e;color:var(--dim);margin-right:5px}
.tag.b{background:#12301c;color:#7ee2a8}.tag.j{background:#3a1d1d;color:#ffb4b4}
.tag.c{background:#2c2410;color:#ffd77a}
.f{border-left:3px solid var(--acc);padding:8px 11px;margin:9px 0;background:#141821}
.f.opinion{border-color:var(--warn)}
.f.prop{border-color:var(--ok)}
.f p{margin:5px 0 0;color:var(--dim);font-size:12.5px}
.ev{color:#7d8590;font-size:11.5px;margin-top:5px;max-height:78px;overflow:auto}
button{background:#21262d;color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:4px 12px;cursor:pointer;font-size:12px;margin-right:6px}
button:hover{border-color:var(--acc)}
button.ok{border-color:#1f6f34;color:#7ee2a8}
button.no{border-color:#6e2b2b;color:#ffb4b4}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td,th{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left;vertical-align:top}
th{color:var(--dim);font-weight:500}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.trace{font-size:11px;color:var(--dim)}
.trace.eng{color:var(--warn)}
</style></head><body>
<header>
  <h1>训练台 · 自我的发展</h1>
  <div class="sub" id="stamp">加载中…</div>
</header>
<main id="app"></main>
<script>
const $ = s => document.querySelector(s);
const esc = s => (s==null?'':String(s)).replace(/[&<>]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const pct = v => Math.max(0,Math.min(1,v||0))*100;

function bar(name, v, src){
  const col = v>=.65?'#3fb950':(v<=.35?'#f85149':'#58a6ff');
  return `<div class="row" title="${esc(src)}">
    <span class="nm">${esc(name)}</span>
    <span class="bar"><i style="width:${pct(v)}%;background:${col}"></i></span>
    <span class="vl">${(v||0).toFixed(2)}</span></div>`;
}

function spark(traj, key, color){
  if(!traj.length) return '';
  const w=340,h=54,pad=3;
  const vs = traj.map(d=>d[key]);
  const lo=Math.min(...vs), hi=Math.max(...vs), rng=(hi-lo)||1;
  const pts = vs.map((v,i)=>{
    const x = pad + i*(w-2*pad)/Math.max(1,vs.length-1);
    const y = h-pad - (v-lo)/rng*(h-2*pad);
    return x.toFixed(1)+','+y.toFixed(1);
  }).join(' ');
  return `<svg width="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"
    style="display:block;margin:4px 0">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6"/>
    <text x="2" y="9" fill="#8a9099" font-size="9">${hi.toFixed(2)}</text>
    <text x="2" y="${h-2}" fill="#8a9099" font-size="9">${lo.toFixed(2)}</text>
  </svg>`;
}

function render(d){
  $('#stamp').textContent = `更新于 ${d.now}　|　数据源 state/train/`;
  const c = d.counts;
  let h = '';

  // ---- 训练进度
  h += `<section class="card"><h2>训练进度</h2><div class="kpi">
    <div><b>${c.turns}</b><span>训练轮次</span></div>
    <div><b>${c.sessions}</b><span>会话</span></div>
    <div><b>${c.rounds}</b><span>训练轮(round)</span></div>
    <div><b>${c.evals}</b><span>训练师评价</span></div>
    <div><b>${d.progress.tutor?'开':'关'}</b><span>训练师驱动</span></div>
    <div><b>${d.progress.seconds||'—'}</b><span>上次耗时(s)</span></div>
  </div>
  <p class="sub">输入来源：${esc(d.progress.source||'—')}　|　输入池 ${d.progress.pool||0} 条　|　
  上次运行 ${esc(d.progress.last_run||'—')}</p>`;

  // ---- 性格
  h += `<section class="card"><h2>性格（极性变量 · 当下状态）</h2>`;
  const pn = d.polarity_names, ps = d.polarity_source;
  for(const k of Object.keys(d.polarity)) h += bar(pn[k]||k, d.polarity[k], ps[k]||'');
  h += `<p class="sub">读自机制层当下状态（不是累积占比）。来源：
    ${Object.values(ps).slice(0,2).map(esc).join('；')}…</p>`;
  h += `<h2 style="margin-top:14px">状态轨迹（每轮）</h2>`;
  const cols = {w:'#58a6ff',l:'#3fb950',tn:'#d29922',s:'#f85149'};
  const nm = {w:'想要',l:'喜欢',tn:'张力',s:'结构压力'};
  for(const k in cols){
    h += `<div class="sub" style="margin-top:6px">${nm[k]}</div>` + spark(d.trajectory,k,cols[k]);
  }
  h += `</section>`;

  // ---- 里程碑
  h += `<section class="card"><h2>里程碑（固化后不退回）</h2>`;
  if(!d.milestones.length) h += `<p class="sub">还没有。需要某类动作重复到阈值，且反应方向有据。</p>`;
  for(const m of d.milestones){
    const fell = (m.current!=null && m.peak!=null && m.current < m.peak);
    h += `<div class="f"><b>${esc(m.text)}</b>
      <div class="sub" style="margin-top:4px">证据 当前 <b>${m.current}</b>
      ${fell?`｜历史最高 <b style="color:var(--warn)">${m.peak}</b>`:''}｜${esc(m.era||'')}</div>
      ${m.basis&&m.basis.n?`<p>依据：做这个动作 ${m.basis.acted} 次；有反应 ${m.basis.n} 次里
      接得住 ${m.basis.continue}、停在那儿 ${m.basis.stop}（${Math.round((m.basis.share||0)*100)}%）；
      基线 ${Math.round((m.basis.baseline_share||0)*100)}%</p>`:''}
    </div>`;
  }
  h += `</section>`;

  // ---- 管理员队列
  const q = d.queue;
  h += `<section class="card full"><h2>管理员队列　<span class="sub">生成于 ${esc(q.generated||'—')}</span></h2>`;
  h += `<div class="warnbox">依据分两层，<b>权重完全不同</b>：
    <b>事实层</b>（可观察）能作为改动依据；<b>意见层</b>（训练师的评价）只作线索，
    指出该去看哪里 —— 拿模型的意见改系统就是模型自己给自己判卷。
    每轮少于 ${d.min_turns} 时，系统会明说「样本不足」而不是报结论。</div>`;

  h += `<h2 style="margin-top:14px">提案（只有事实层能生成）</h2>`;
  if(!q.proposals.length) h += `<p class="sub">没有提案。</p>`;
  q.proposals.forEach(p=>{
    const eng = (p.trace||'') === 'ENG';
    h += `<div class="f prop"><b>${esc(p.pid)}</b>　${esc(p.summary)}
      <span class="trace ${eng?'eng':''}">［依据：${esc(p.trace||'?')}］</span>
      ${eng?`<span class="trace eng">← 追溯不到书里的出处，必须你批</span>`:''}
      <p>${esc(p.detail)}</p>
      <div class="ev mono">${esc(JSON.stringify(p.evidence||[],null,0)).slice(0,400)}</div>
      <div style="margin-top:8px">
        <button class="ok" onclick="decide('${p.pid}',1,this)">批准</button>
        <button class="no" onclick="decide('${p.pid}',0,this)">驳回</button>
      </div></div>`;
  });

  h += `<h2 style="margin-top:16px">事实层发现</h2>`;
  (q.facts||[]).forEach(f=>{
    h += `<div class="f"><b>${esc(f.title)}</b>
      <p>${esc(f.detail)}</p>
      <div class="ev mono">${esc(JSON.stringify(f.evidence||[]).slice(0,340))}</div></div>`;
  });

  h += `<h2 style="margin-top:16px">意见层（训练师的评价 · 只作线索）</h2>`;
  if(!(q.opinions||[]).length) h += `<p class="sub">训练师没提出问题。</p>`;
  (q.opinions||[]).forEach(f=>{
    h += `<div class="f opinion"><b>${esc(f.title)}</b><p>${esc(f.detail)}</p>
      <div class="ev mono">${esc(JSON.stringify(f.evidence||[]).slice(0,600))}</div></div>`;
  });
  h += `</section>`;

  // ---- 交流记录
  h += `<section class="card full"><h2>交流记录（最近 ${d.turns.length} 轮）</h2><div>`;
  d.turns.slice().reverse().forEach(t=>{
    const bad = t.judge && t.judge!=='none';
    h += `<div class="turn">
      <div class="i">› ${esc(t.input)}</div>
      <div class="o">${esc(t.output).replace(/\n/g,'<br>')}</div>
      <div style="margin-top:5px">
        <span class="tag">${esc(t.channel)}</span>
        <span class="tag b">${esc(t.behavior)}</span>
        ${t.markers.map(m=>`<span class="tag">${esc(m)}</span>`).join('')}
        ${t.char_note?`<span class="tag c">性格介入</span>`:''}
        ${t.judge?`<span class="tag j">训练师：${esc(t.judge)}</span>
          <span class="sub">${esc(t.judge_why)}</span>`:''}
      </div>
      ${t.notes.length?`<div class="trace">${esc(t.notes.join(' ｜ '))}</div>`:''}
    </div>`;
  });
  if(!d.turns.length) h += `<p class="sub">还没有训练数据。跑一次：<span class="mono">python engine/train.py --tutor --rounds 1</span></p>`;
  h += `</div></section>`;

  // ---- 决定历史
  h += `<section class="card full"><h2>我的决定（只追加，不删）</h2>`;
  if(!d.decisions.length) h += `<p class="sub">还没有做过决定。</p>`;
  else{
    h += `<table><tr><th>时间</th><th>提案</th><th>决定</th><th>内容</th></tr>`;
    d.decisions.slice().reverse().forEach(x=>{
      h += `<tr><td class="mono">${esc(x.ts)}</td><td>${esc(x.pid)}</td>
        <td>${x.decision==='approve'?'✅ 批准':'❌ 驳回'}</td><td>${esc(x.title)}</td></tr>`;
    });
    h += `</table>`;
  }
  h += `</section>`;

  $('#app').innerHTML = h;
}

async function load(){ const r = await fetch('/api/state'); render(await r.json()); }
async function decide(pid, approve, btn){
  btn.disabled = true; btn.textContent = '…';
  await fetch('/api/decide', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({pid, approve})});
  load();
}
load(); setInterval(load, 15000);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                      # noqa: N802
        if self.path.startswith("/api/state"):
            try:
                d = collect()
            except Exception as e:                 # noqa: BLE001
                d = {"error": repr(e)[:200]}
            self._send(200, json.dumps(d, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self) -> None:                     # noqa: N802
        if not self.path.startswith("/api/decide"):
            self._send(404, b"no", "text/plain")
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                          # noqa: BLE001
            req = {}
        pid = str(req.get("pid") or "")
        approve = bool(req.get("approve"))
        title, sid, kind, fp = "", "", "", None
        q = _json(os.path.join(TRAIN_DIR, "review_queue.json"), {}) or {}
        fp = q.get("fingerprint")
        for p in q.get("proposals", []):
            if p.get("pid") == pid:
                title = p.get("summary", "")
                sid = p.get("sid", "")          # ★ 稳定主键（用户裁定 2026-10-02）
                kind = p.get("kind", "")
                break
        try:
            import admin as A
            A.log_decision(pid, approve, title, sid=sid, kind=kind, fp=fp)
            ok = True
        except Exception as e:                     # noqa: BLE001
            ok = repr(e)[:120]
        self._send(200, json.dumps({"ok": ok}, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def log_message(self, *a) -> None:             # 别把访问日志刷到控制台
        pass


class _Srv(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(port: int = DEFAULT_PORT) -> int:
    if not os.path.isdir(TRAIN_DIR):
        os.makedirs(TRAIN_DIR, exist_ok=True)
    httpd = _Srv(("127.0.0.1", port), Handler)
    print("=" * 66)
    print("训练台已启动：http://127.0.0.1:%d" % port)
    print("数据源：%s" % TRAIN_DIR)
    print("按 Ctrl+C 停止。面板只读，除了记录你的批准/驳回。")
    print("=" * 66)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="训练台可视化面板")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    a = ap.parse_args()
    raise SystemExit(serve(a.port))
