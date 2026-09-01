from __future__ import annotations

import ast
import html
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT / "vendor" / "micrograd", ROOT / "vendor" / "minbpe"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# These are pinned source submodules, not writable runtime caches.  Import them
# without creating __pycache__ entries inside the vendor checkouts; otherwise a
# normal plugin load makes the superproject appear dirty.
_prev_dont_write_bytecode = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    from micrograd.engine import Value  # type: ignore
    from minbpe.basic import BasicTokenizer  # type: ignore
finally:
    sys.dont_write_bytecode = _prev_dont_write_bytecode


class AILabError(ValueError):
    pass


def _collect_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id != "relu":
            out.add(n.id)
    return out


def _build(node: ast.AST, env: dict[str, Value]) -> Value:
    if isinstance(node, ast.Expression): return _build(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return Value(float(node.value))
    if isinstance(node, ast.Name):
        if node.id not in env: raise AILabError(f"变量 {node.id} 没有赋值")
        return env[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_build(node.operand, env)
    if isinstance(node, ast.BinOp):
        a = _build(node.left, env); b = _build(node.right, env)
        if isinstance(node.op, ast.Add): return a + b
        if isinstance(node.op, ast.Sub): return a - b
        if isinstance(node.op, ast.Mult): return a * b
        if isinstance(node.op, ast.Div): return a / b
        if isinstance(node.op, ast.Pow):
            if not isinstance(node.right, ast.Constant) or not isinstance(node.right.value, (int, float)): raise AILabError("指数必须是数值常量")
            exp = float(node.right.value)
            if abs(exp) > 12: raise AILabError("指数绝对值最多 12")
            return a ** exp
        raise AILabError("仅支持 + - * / **")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "relu" and len(node.args) == 1 and not node.keywords:
        return _build(node.args[0], env).relu()
    raise AILabError(f"不支持的表达式节点：{type(node).__name__}")


def _trace(root: Value) -> list[Value]:
    nodes: list[Value] = []; seen: set[int] = set()
    def visit(v: Value):
        if id(v) in seen: return
        seen.add(id(v))
        for child in v._prev: visit(child)
        nodes.append(v)
    visit(root); return nodes


def render_grad(output_dir: Path, expr: str, assignments: dict[str, float]) -> tuple[Path, str]:
    expr = (expr or "").strip()
    if not expr or len(expr) > 1000: raise AILabError("表达式需为 1-1000 字符")
    try: tree = ast.parse(expr, mode="eval")
    except SyntaxError as e: raise AILabError(f"表达式语法错误：{e.msg}") from e
    names = _collect_names(tree)
    if len(names) > 12: raise AILabError("变量最多 12 个")
    missing = sorted(names - assignments.keys())
    if missing: raise AILabError("缺少变量赋值：" + ", ".join(missing) + "；例如 `| x=2 y=3`")
    env: dict[str, Value] = {}
    for name in sorted(names):
        value = float(assignments[name])
        if not math.isfinite(value) or abs(value) > 1e9: raise AILabError(f"{name} 的值不合法")
        v = Value(value); v.label = name; env[name] = v
    out = _build(tree, env); nodes = _trace(out)
    if len(nodes) > 120: raise AILabError("计算图超过 120 个节点，请简化表达式")
    out.backward(); node_ids = {id(v): f"n{i}" for i, v in enumerate(nodes)}
    lines = ["digraph G {", "rankdir=LR;", 'graph [bgcolor="white", pad="0.25"];', 'node [shape=record, fontname="DejaVu Sans", fontsize=10];']
    for v in nodes:
        nid = node_ids[id(v)]; label = getattr(v, "label", "") or (v._op if v._op else "value")
        label = html.escape(str(label), quote=True).replace("{", "(").replace("}", ")")
        lines.append(f'{nid} [label="{{{label}|data {v.data:.6g}|grad {v.grad:.6g}}}"];')
        for c in v._prev: lines.append(f"{node_ids[id(c)]} -> {nid};")
    lines.append("}")
    outdir = Path(output_dir) / "ai"; outdir.mkdir(parents=True, exist_ok=True); path = outdir / "micrograd.png"
    try: cp = subprocess.run(["dot", "-Tpng", "-Gdpi=150"], input="\n".join(lines).encode(), capture_output=True, timeout=8, check=False)
    except FileNotFoundError as e: raise AILabError("缺少 Graphviz `dot`") from e
    if cp.returncode != 0 or not cp.stdout.startswith(b"\x89PNG"): raise AILabError("Graphviz 渲染失败：" + cp.stderr.decode("utf-8", "replace")[:500])
    path.write_bytes(cp.stdout)
    grads = ", ".join(f"dout/d{name}={env[name].grad:.6g}" for name in sorted(env)) or "无变量"
    return path, f"micrograd · out={out.data:.6g} · {grads} · {len(nodes)} nodes"


def _font(size: int):
    from PIL import ImageFont
    candidates = ["/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/dejavu/DejaVuSans.ttf"]
    for p in candidates:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()


def render_bpe(output_dir: Path, text: str, merges: int = 20) -> tuple[Path, str]:
    text = (text or "").strip("\n")
    if not text: raise AILabError("BPE 文本不能为空")
    raw = text.encode("utf-8")
    if len(raw) > 5000: raise AILabError("BPE 输入最多 5000 UTF-8 bytes")
    merges = max(0, min(int(merges), 48, max(0, len(raw) - 1)))
    tok = BasicTokenizer(); tok.train(text, 256 + merges, verbose=False); ids = tok.encode(text)
    pieces = []
    for tid in ids:
        b = tok.vocab[tid]
        try:
            s = b.decode("utf-8").replace("\n", "\\n").replace("\t", "\\t")
        except UnicodeDecodeError:
            s = "[" + " ".join(f"{x:02x}" for x in b[:10]) + (" ..." if len(b) > 10 else "") + "]"
        if len(s) > 18: s = s[:15] + "…"
        pieces.append((tid, s, len(b)))
    from PIL import Image, ImageDraw
    W = 1280; margin = 36; title_font = _font(30); small = _font(19); token_font = _font(22)
    rows=[]; cur=[]; used=0
    for tid,s,nbytes in pieces:
        cw=max(110,min(330,70+len(s)*24))
        if cur and used+cw+10 > W-2*margin: rows.append(cur); cur=[]; used=0
        cur.append((tid,s,nbytes,cw)); used += cw+10
    if cur: rows.append(cur)
    clipped=len(rows)>18; rows=rows[:18]; H = 150 + len(rows)*82 + 90
    im=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(im)
    d.text((margin,24),"minBPE · byte-level tokenization",font=title_font,fill="black")
    ratio=len(raw)/max(1,len(ids)); d.text((margin,70),f"UTF-8 bytes: {len(raw)}   merges: {len(tok.merges)}   tokens: {len(ids)}   bytes/token: {ratio:.2f}",font=small,fill=(60,60,60))
    y=118
    for row in rows:
        x=margin
        for tid,s,nbytes,cw in row:
            d.rounded_rectangle((x,y,x+cw,y+60),radius=10,fill=(244,246,250),outline=(180,186,198),width=2)
            d.text((x+10,y+7),s or "∅",font=token_font,fill=(20,20,20)); d.text((x+10,y+37),f"id {tid} · {nbytes}B",font=small,fill=(90,90,100)); x += cw+10
        y += 82
    if clipped: d.text((margin,H-62),"token rows truncated for chat preview",font=small,fill=(130,70,30))
    else:
        preview=[]
        for pair,tid in list(tok.merges.items())[:8]:
            a=tok.vocab[pair[0]].decode("utf-8",errors="replace").replace("\n","\\n"); b=tok.vocab[pair[1]].decode("utf-8",errors="replace").replace("\n","\\n"); c=tok.vocab[tid].decode("utf-8",errors="replace").replace("\n","\\n")
            preview.append(f"[{a}] + [{b}] → [{c}]")
        if preview: d.text((margin,H-62),"first merges: " + "  ·  ".join(preview)[:150],font=small,fill=(70,70,80))
    outdir=Path(output_dir)/"ai"; outdir.mkdir(parents=True,exist_ok=True); path=outdir/"minbpe.png"; im.save(path,"PNG",optimize=True)
    return path, f"minBPE · {len(raw)} bytes → {len(ids)} tokens · {ratio:.2f} bytes/token · {len(tok.merges)} merges"
