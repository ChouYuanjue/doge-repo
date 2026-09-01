from __future__ import annotations

import math
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYFORMLANG = ROOT / "vendor" / "pyformlang"
if str(PYFORMLANG) not in sys.path:
    sys.path.insert(0, str(PYFORMLANG))

from pyformlang.regular_expression import PythonRegex  # type: ignore
import networkx as nx
from networkx.algorithms.link_analysis.pagerank_alg import _pagerank_python


class CSLabError(ValueError):
    pass


def _q(s: object) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _render_dot(dot: str, output: Path) -> None:
    try:
        cp = subprocess.run(["dot", "-Tpng", "-Gdpi=145"], input=dot.encode("utf-8"), capture_output=True, timeout=10, check=False)
    except FileNotFoundError as e:
        raise CSLabError("缺少 Graphviz `dot`") from e
    if cp.returncode != 0 or not cp.stdout.startswith(b"\x89PNG"):
        raise CSLabError("Graphviz 渲染失败：" + cp.stderr.decode("utf-8", "replace")[:600])
    output.write_bytes(cp.stdout)


def _automaton_dot(automaton, title: str) -> str:
    states = list(automaton.states)
    if len(states) > 120:
        raise CSLabError(f"{title} 有 {len(states)} 个状态，超过群聊可视化上限 120；请简化正则")
    ordered = sorted(states, key=lambda s: str(getattr(s, "value", s)))
    ids = {s: f"q{i}" for i, s in enumerate(ordered)}
    starts = set(automaton.start_states)
    finals = set(automaton.final_states)
    grouped: dict[tuple[object, object], list[str]] = defaultdict(list)
    for a, sym, b in automaton._transition_function.get_edges():
        sv = str(getattr(sym, "value", sym))
        if sv in {"epsilon", "$", "ε"} or sym.__class__.__name__.lower() == "epsilon":
            sv = "ε"
        if sv not in grouped[(a, b)]: grouped[(a, b)].append(sv)
    lines = [
        "digraph G {", "rankdir=LR;", 'graph [bgcolor="white", pad="0.25", labelloc="t", fontsize=18, fontname="DejaVu Sans"];',
        f'label="{_q(title)}";', 'node [shape=circle, fontname="DejaVu Sans", fontsize=11];', 'edge [fontname="DejaVu Sans", fontsize=10];'
    ]
    for s in ordered:
        attrs = [f'label="{ids[s]}"']
        if s in finals: attrs.append("peripheries=2")
        lines.append(f'{ids[s]} [{", ".join(attrs)}];')
    for i, s in enumerate(sorted(starts, key=lambda x: ids[x])):
        lines.append(f'start{i} [shape=point, width=0.08, label=""]; start{i} -> {ids[s]};')
    for (a,b), labels in grouped.items():
        label = ", ".join(sorted(labels))
        if len(label) > 90: label = label[:87] + "…"
        lines.append(f'{ids[a]} -> {ids[b]} [label="{_q(label)}"];')
    lines.append("}")
    return "\n".join(lines)


def render_regex(output_dir: Path, pattern: str) -> tuple[list[Path], str]:
    pattern = (pattern or "").strip()
    if not pattern or len(pattern) > 500:
        raise CSLabError("regex 需为 1-500 字符")
    try:
        regex = PythonRegex(pattern)
        nfa = regex.to_epsilon_nfa()
        dfa = nfa.to_deterministic()
        mini = dfa.minimize()
    except Exception as e:
        raise CSLabError(f"正则解析/自动机构造失败：{str(e)[:700]}") from e
    counts = (len(nfa.states), len(dfa.states), len(mini.states))
    if max(counts) > 120:
        raise CSLabError(f"状态爆炸：ε-NFA/DFA/min-DFA = {counts[0]}/{counts[1]}/{counts[2]}，超过 120 状态上限")
    out = Path(output_dir) / "cs"; out.mkdir(parents=True, exist_ok=True)
    paths=[]
    for name, automaton, title in [
        ("nfa", nfa, f"ε-NFA · {counts[0]} states"),
        ("dfa", dfa, f"DFA · {counts[1]} states"),
        ("min", mini, f"Minimized DFA · {counts[2]} states"),
    ]:
        p=out/f"regex-{name}.png"; _render_dot(_automaton_dot(automaton,title),p); paths.append(p)
    caption=f"PythonRegex · ε-NFA {counts[0]} → DFA {counts[1]} → min-DFA {counts[2]} states"
    return paths,caption


_EDGE_RE = re.compile(r"^([^>:\s,]+)\s*(?:->|>)\s*([^>:\s,]+)(?::([0-9.]+))?$")

def _parse_edges(spec: str):
    spec=(spec or "").strip()
    if not spec or len(spec)>4000: raise CSLabError("PageRank 图描述需为 1-4000 字符")
    edges=[]
    for item in re.split(r"[,;\n]+",spec):
        item=item.strip()
        if not item: continue
        m=_EDGE_RE.match(item)
        if not m: raise CSLabError(f"无法解析边 `{item}`；格式如 A>B 或 A>B:2")
        a,b,w=m.groups(); weight=float(w or 1.0)
        if not math.isfinite(weight) or weight<=0 or weight>1e6: raise CSLabError("边权必须为正有限数")
        edges.append((a,b,weight))
    if not edges: raise CSLabError("至少需要一条边")
    nodes={x for a,b,_ in edges for x in (a,b)}
    if len(nodes)>60 or len(edges)>240: raise CSLabError("群聊 PageRank 最多 60 个节点 / 240 条边")
    return edges


def render_pagerank(output_dir: Path, spec: str, alpha: float=0.85) -> tuple[Path,str]:
    edges=_parse_edges(spec); alpha=float(alpha)
    if not 0.05<=alpha<=0.99: raise CSLabError("alpha 需在 0.05..0.99")
    g=nx.DiGraph()
    for a,b,w in edges: g.add_edge(a,b,weight=w)
    try: ranks=_pagerank_python(g,alpha=alpha,weight="weight",max_iter=200,tol=1e-10)
    except Exception as e: raise CSLabError(f"PageRank 计算失败：{e}") from e
    maxr=max(ranks.values()) if ranks else 1
    lines=["digraph G {","rankdir=LR;",'graph [bgcolor="white", pad="0.3", labelloc="t"];',f'label="PageRank · alpha={alpha:.2f}";', 'node [shape=circle, style=filled, fontname="DejaVu Sans"];','edge [fontname="DejaVu Sans"];']
    for node,r in sorted(ranks.items(),key=lambda kv:-kv[1]):
        size=0.55+1.35*r/maxr; shade=int(245-85*r/maxr); fill=f"#{shade:02x}{min(250,shade+15):02x}ff"
        lines.append(f'"{_q(node)}" [label="{_q(node)}\\n{r:.3f}", width={size:.2f}, height={size:.2f}, fixedsize=true, fillcolor="{fill}"];')
    for a,b,w in edges:
        label="" if abs(w-1)<1e-12 else f' [label="{w:g}"]'
        lines.append(f'"{_q(a)}" -> "{_q(b)}"{label};')
    lines.append("}")
    out=Path(output_dir)/"cs"; out.mkdir(parents=True,exist_ok=True); p=out/"pagerank.png"; _render_dot("\n".join(lines),p)
    top=", ".join(f"{n}={r:.3f}" for n,r in sorted(ranks.items(),key=lambda kv:-kv[1])[:6])
    return p,f"PageRank · {len(ranks)} nodes · {len(edges)} edges · {top}"
