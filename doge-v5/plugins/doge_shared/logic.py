from __future__ import annotations

import ast
import base64
import operator
import re
from urllib.parse import quote, unquote

BASE64_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+/"
MAX_EXPR_LEN = 512
MAX_ABS_RESULT = 10**100
MAX_POWER = 1000
MAX_BAN_SECONDS = 30 * 24 * 60 * 60

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Invert: operator.invert}


def _check_number(value):
    if isinstance(value, complex) or not isinstance(value, (int, float)):
        raise ValueError("只允许实数运算")
    if abs(value) > MAX_ABS_RESULT:
        raise ValueError("结果过大")
    return value


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return _check_number(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _check_number(_UNARY_OPS[type(node.op)](_eval_node(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_POWER:
            raise ValueError("指数过大")
        if isinstance(node.op, (ast.LShift, ast.RShift)) and (not isinstance(right, int) or right < 0 or right > 4096):
            raise ValueError("位移量不合法")
        return _check_number(_BIN_OPS[type(node.op)](left, right))
    raise ValueError(f"不支持的表达式节点: {type(node).__name__}")


def safe_calc(expression: str):
    expression = expression.strip()
    if not expression or len(expression) > MAX_EXPR_LEN:
        raise ValueError("表达式为空或过长")
    # Preserve v3 semantics: ^ is power; textual xor remains bitwise xor.
    normalized = re.sub(r"\bxor\b", "__XOR__", expression, flags=re.I)
    normalized = normalized.replace("×", "*").replace("÷", "/").replace("^", "**")
    normalized = normalized.replace("__XOR__", "^")
    tree = ast.parse(normalized, mode="eval")
    return _eval_node(tree)


def _validate_base(base: int) -> None:
    if not 2 <= base <= 64:
        raise ValueError("进制必须在 2 到 64 之间")


def parse_base_number(text: str, base: int) -> int:
    _validate_base(base)
    raw = text.strip()
    sign = -1 if raw.startswith("-") else 1
    if raw[:1] in "+-":
        raw = raw[1:]
    if not raw:
        raise ValueError("数字为空")
    value = 0
    alphabet = BASE64_DIGITS[:base]
    for ch in raw:
        idx = alphabet.find(ch)
        if idx < 0:
            raise ValueError(f"字符 {ch!r} 不属于 {base} 进制")
        value = value * base + idx
    return sign * value


def format_base_number(value: int, base: int) -> str:
    _validate_base(base)
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    n = abs(value)
    out = []
    digits = BASE64_DIGITS[:base]
    while n:
        n, rem = divmod(n, base)
        out.append(digits[rem])
    return sign + "".join(reversed(out))


def convert_base(text: str, source_base: int, target_base: int) -> str:
    return format_base_number(parse_base_number(text, source_base), target_base)


def codec(action: str, kind: str, text: str) -> str:
    action, kind = action.lower(), kind.lower()
    if action not in {"encode", "decode"}:
        raise ValueError("action 必须是 encode 或 decode")
    if kind == "url":
        return quote(text, safe="") if action == "encode" else unquote(text)
    if kind in {"unicode", "usc2", "ucs2"}:
        if action == "encode":
            return text.encode("unicode_escape").decode("ascii")
        return bytes(text, "utf-8").decode("unicode_escape")
    if kind == "hex":
        return text.encode("utf-8").hex() if action == "encode" else bytes.fromhex(text).decode("utf-8")
    if kind == "base64":
        if action == "encode":
            return base64.b64encode(text.encode("utf-8")).decode("ascii")
        return base64.b64decode(text.encode("ascii"), validate=True).decode("utf-8")
    raise ValueError("支持 url / unicode(usc2) / hex / base64")


def parse_ban_duration(text: str) -> int:
    """Parse legacy Chinese duration or compact English units, capped at 30 days."""
    s = text.strip().lower()
    if not s:
        return 60
    if "年" in s or "月" in s:
        return MAX_BAN_SECONDS
    total = 0
    matched = False
    patterns = [
        (r"(\d+)\s*(?:天|d(?:ays?)?)", 86400),
        (r"(\d+)\s*(?:小时|时|h(?:ours?)?)", 3600),
        (r"(\d+)\s*(?:分钟|分|min(?:utes?)?|m)", 60),
        (r"(\d+)\s*(?:秒钟|秒|s(?:ec(?:onds?)?)?)", 1),
    ]
    for pattern, multiplier in patterns:
        for m in re.finditer(pattern, s):
            total += int(m.group(1)) * multiplier
            matched = True
    if not matched:
        # A bare integer keeps the old user expectation of minutes.
        m = re.fullmatch(r"\s*(\d+)\s*", s)
        if m:
            total = int(m.group(1)) * 60
            matched = True
    if not matched or total <= 0:
        raise ValueError("时间格式示例：10分、2小时30分、90s")
    return min(total, MAX_BAN_SECONDS)
