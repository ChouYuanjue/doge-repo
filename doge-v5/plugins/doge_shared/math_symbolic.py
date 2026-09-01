from __future__ import annotations

import math
import re
import statistics
from urllib.parse import quote

MAX_SYMBOLIC_LEN = 600
_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_ALLOWED_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "Abs", "floor", "ceiling", "factorial", "gamma",
}
_ALLOWED_CONSTANTS = {"pi", "E", "I", "oo"}


def _sp():
    try:
        import sympy as sp
    except Exception as exc:
        raise RuntimeError("符号数学需要 SymPy") from exc
    return sp


def _validate_source(source: str) -> str:
    text = str(source or "").strip()
    if not text or len(text) > MAX_SYMBOLIC_LEN:
        raise ValueError("数学表达式为空或过长")
    if any(ch in text for ch in "[]{};'\"\\`@:$") or "__" in text:
        raise ValueError("表达式包含不允许的语法")
    # Dots are only allowed as decimal points between digits. This blocks
    # attribute access while keeping ordinary floating-point constants.
    for i, ch in enumerate(text):
        if ch == "." and not (i and i + 1 < len(text) and text[i - 1].isdigit() and text[i + 1].isdigit()):
            raise ValueError("表达式中的 . 只能用于小数")
    for m in _IDENT.finditer(text):
        name = m.group(0)
        tail = text[m.end():].lstrip()
        if tail.startswith("(") and name not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"不允许调用函数 {name}")
    return text.replace("^", "**")


def parse_expr(source: str):
    sp = _sp()
    text = _validate_source(source)
    local = {name: getattr(sp, name) for name in _ALLOWED_FUNCTIONS if hasattr(sp, name)}
    local.update({"pi": sp.pi, "E": sp.E, "I": sp.I, "oo": sp.oo})
    # Unknown bare identifiers intentionally become Symbols; function calls are
    # separately allow-listed above.
    for name in set(_IDENT.findall(text)):
        if name not in local:
            local[name] = sp.Symbol(name)
    return sp.sympify(text, locals=local, evaluate=True)


def _symbol(name: str):
    raw = str(name or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", raw):
        raise ValueError("变量名需为简单英文字母/数字标识符，例如 x 或 x1")
    return _sp().Symbol(raw)


def numeric(source: str, digits: int = 15) -> str:
    digits = int(digits)
    if not 2 <= digits <= 100:
        raise ValueError("数值精度需在 2..100 位")
    return str(_sp().N(parse_expr(source), digits))


def simplify(source: str) -> str:
    return str(_sp().simplify(parse_expr(source)))


def expand(source: str) -> str:
    return str(_sp().expand(parse_expr(source)))


def factor(source: str) -> str:
    return str(_sp().factor(parse_expr(source)))


def solve(source: str, variable: str = "x") -> str:
    sp = _sp(); var = _symbol(variable)
    if "=" in source:
        left, right = source.split("=", 1)
        expr = sp.Eq(parse_expr(left), parse_expr(right))
    else:
        expr = parse_expr(source)
    roots = sp.solve(expr, var)
    return f"{variable} = " + (", ".join(str(x) for x in roots) if roots else "∅")


def diff(source: str, variable: str = "x", order: int = 1) -> str:
    order = int(order)
    if not 1 <= order <= 12:
        raise ValueError("求导阶数需在 1..12")
    return str(_sp().diff(parse_expr(source), _symbol(variable), order))


def integrate(source: str, variable: str = "x", lower: str | None = None, upper: str | None = None) -> str:
    sp = _sp(); expr = parse_expr(source); var = _symbol(variable)
    if (lower is None) != (upper is None):
        raise ValueError("定积分需要同时提供下限和上限")
    if lower is None:
        return str(sp.integrate(expr, var))
    return str(sp.integrate(expr, (var, parse_expr(lower), parse_expr(upper))))


def limit(source: str, variable: str, point: str, direction: str = "+-") -> str:
    direction = str(direction or "+-").strip()
    if direction not in {"+", "-", "+-"}:
        raise ValueError("方向只能是 +、- 或 +-")
    return str(_sp().limit(parse_expr(source), _symbol(variable), parse_expr(point), dir=direction))


def factorint(value: int) -> str:
    n = int(value)
    if abs(n) > 10**30:
        raise ValueError("整数过大；当前轻量分解限制为 |n| <= 10^30")
    fs = _sp().factorint(n)
    return " × ".join(f"{p}^{e}" if e != 1 else str(p) for p, e in fs.items()) or str(n)


def prime(value: int) -> str:
    sp = _sp(); n = int(value)
    if abs(n) > 10**100:
        raise ValueError("整数过大")
    if n < 2:
        return f"{n} 不是素数"
    if sp.isprime(n):
        return f"{n} 是素数"
    return f"{n} 不是素数；上一素数 {sp.prevprime(n)}，下一素数 {sp.nextprime(n)}"


def stats(values: list[float]) -> str:
    xs = [float(x) for x in values]
    if not 1 <= len(xs) <= 5000 or not all(math.isfinite(x) for x in xs):
        raise ValueError("统计输入需为 1..5000 个有限实数")
    mean = statistics.fmean(xs); median = statistics.median(xs)
    popstd = statistics.pstdev(xs) if len(xs) > 1 else 0.0
    samplestd = statistics.stdev(xs) if len(xs) > 1 else 0.0
    return f"n={len(xs)}\nmean={mean:g}\nmedian={median:g}\npopulation std={popstd:g}\nsample std={samplestd:g}\nmin={min(xs):g}\nmax={max(xs):g}"


_FORMAL = {
    "lean": {
        "name": "Lean 4 / Mathlib",
        "url": "https://live.lean-lang.org/",
        "template": "import Mathlib\n\nexample (a b : ℝ) : (a + b)^2 = a^2 + 2*a*b + b^2 := by\n  ring",
        "note": "轻量入口使用 Lean Web；Doge 只生成/转交源码，不把网页结果冒充本地 kernel 验证。",
    },
    "coq": {
        "name": "Coq / Rocq via jsCoq",
        "url": "https://coq.vercel.app/",
        "template": "Example plus_0_r : forall n : nat, n + 0 = n.\nProof.\n  intros n. induction n; simpl; auto.\nQed.",
        "note": "轻量入口使用浏览器内 jsCoq；当前不在 Doge 服务器安装 Rocq/Coq toolchain。",
    },
    "rzk": {
        "name": "Rzk",
        "url": "https://rzk-lang.github.io/rzk/develop/playground",
        "template": "#lang rzk-1\n\n#define id (A : U) : A → A\n  := \\ x → x",
        "note": "Rzk 面向 synthetic ∞-categories/homotopy type theory；这里提供单文件 playground 入口，不声称本地核验。",
    },
}


def formal(language: str, code: str = "") -> str:
    lang = str(language or "").strip().lower()
    if lang in {"rocq"}: lang = "coq"
    if lang not in _FORMAL:
        raise ValueError("形式化语言支持 lean / coq(rocq) / rzk")
    item = _FORMAL[lang]
    source = str(code or "").strip() or item["template"]
    url = item["url"]
    if lang == "lean":
        url += "#project=mathlib-stable&code=" + quote(source, safe="")
    return f"{item['name']}\n{item['note']}\n\nPlayground: {url}\n\nStarter/source:\n{source}"


def formal_overview() -> str:
    return (
        "形式化数学（轻量模式）\n"
        "Lean：通用定理证明 + Mathlib，适合现代形式化数学；可把源码直接带入 Lean Web。\n"
        "Coq/Rocq：成熟依赖类型证明环境；使用 jsCoq 浏览器入口。\n"
        "Rzk：更专门、实验性的 synthetic ∞-categories / HoTT 方向；使用在线 playground。\n"
        "这些入口目前不代表 Doge 本机 kernel 已验证证明；需要严格验真时应在对应 playground/toolchain 实际运行。"
    )
