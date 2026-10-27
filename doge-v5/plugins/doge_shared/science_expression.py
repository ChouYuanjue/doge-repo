"""Strict, bounded AST -> SymPy -> NumPy expression compiler for public lab commands.

No sympify/eval of raw user code: only arithmetic, numeric literals, named
symbols and explicitly whitelisted mathematical functions are admitted.
SymPy's lambdify code generation is applied only to the vetted expression tree.
"""
from __future__ import annotations

import ast
import math
import re
from functools import lru_cache

import numpy as np

from .visual_lab import LabError

_FUNCS = {
    "sin": "sin", "cos": "cos", "tan": "tan",
    "asin": "asin", "acos": "acos", "atan": "atan",
    "sinh": "sinh", "cosh": "cosh", "tanh": "tanh",
    "exp": "exp", "log": "log", "sqrt": "sqrt",
    "abs": "Abs", "Abs": "Abs", "arg": "arg",
    "re": "re", "im": "im", "conjugate": "conjugate",
}
_CONSTANTS = {"pi": "pi", "e": "E", "E": "E", "i": "I", "I": "I"}
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


def parse_formula(source: str, variables: tuple[str, ...]):
    """Parse one bounded arithmetic formula, returning SymPy Expr."""
    import sympy as sp
    source = str(source).strip().replace("^", "**")
    if not source or len(source) > 180:
        raise LabError("表达式为空或超过 180 字符")
    if len(variables) > 20 or any(not _NAME.fullmatch(v) or v in _FUNCS or v in _CONSTANTS for v in variables):
        raise LabError("非法变量名")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise LabError("表达式语法错误；用 ^ 表示幂，例如 z^3+c") from exc
    if sum(1 for _ in ast.walk(tree)) > 110:
        raise LabError("表达式结构过于复杂")
    syms = {v: sp.Symbol(v) for v in variables}
    constants = {k: getattr(sp, v) for k, v in _CONSTANTS.items()}
    funcs = {k: getattr(sp, v) for k, v in _FUNCS.items()}
    budget = [0]

    def make(node, depth=0):
        budget[0] += 1
        if budget[0] > 110 or depth > 20:
            raise LabError("表达式嵌套过深")
        if isinstance(node, ast.Expression):
            return make(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            if not math.isfinite(float(node.value)) or abs(float(node.value)) > 1e9:
                raise LabError("数值常量超出计算限制")
            return sp.Integer(node.value) if isinstance(node.value, int) else sp.Float(node.value)
        if isinstance(node, ast.Name):
            if node.id in syms: return syms[node.id]
            if node.id in constants: return constants[node.id]
            raise LabError(f"未知变量/常量 {node.id}（可用：{', '.join(variables)}）")
        if isinstance(node, ast.UnaryOp) and type(node.op) in {ast.USub, ast.UAdd}:
            result = make(node.operand, depth + 1)
            return -result if isinstance(node.op, ast.USub) else result
        if isinstance(node, ast.BinOp):
            left = make(node.left, depth + 1)
            right = make(node.right, depth + 1)
            if isinstance(node.op, ast.Add): return sp.Add(left, right, evaluate=False)
            if isinstance(node.op, ast.Sub): return sp.Add(left, -right, evaluate=False)
            if isinstance(node.op, ast.Mult): return sp.Mul(left, right, evaluate=False)
            if isinstance(node.op, ast.Div): return sp.Mul(left, sp.Pow(right, -1, evaluate=False), evaluate=False)
            if isinstance(node.op, ast.Pow):
                # User-defined powers must be constant, otherwise a single
                # request could produce enormous symbolic trees / overflow loops.
                if right.free_symbols or not right.is_number or not right.is_real:
                    raise LabError("指数必须是有限实数常量")
                exponent = float(right)
                if not math.isfinite(exponent) or abs(exponent) > 32:
                    raise LabError("指数绝对值不能超过 32")
                return sp.Pow(left, right, evaluate=False)
            raise LabError("只支持 + - * / ^ 运算")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name not in funcs or len(node.args) != 1 or node.keywords:
                raise LabError(f"不允许函数调用 {name}；函数必须是单参数")
            return funcs[name](make(node.args[0], depth + 1), evaluate=False)
        raise LabError("表达式包含不允许的 Python 语法")
    expr = make(tree)
    if expr.count_ops() > 180:
        raise LabError("表达式过于复杂")
    return expr


@lru_cache(maxsize=100)
def compile_formula(source: str, variables: tuple[str, ...]):
    import sympy as sp
    expression = parse_formula(source, variables)
    fn = sp.lambdify([sp.Symbol(v) for v in variables], expression, modules="numpy", docstring_limit=0, cse=False)
    return fn


def compute(source: str, variables: tuple[str, ...], *values, shape=None):
    if len(values) != len(variables):
        raise LabError("表达式变量数与传入数据不匹配")
    with np.errstate(all="ignore"):
        result = np.asarray(compile_formula(source, variables)(*values))
        if shape is not None:
            result = np.broadcast_to(result, shape)
    if result.dtype.kind not in "fcbiu":
        raise LabError("计算结果不是数值")
    return result


def float_opt(value: str | float, name: str, low: float, high: float) -> float:
    try:
        x = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise LabError(f"{name} 必须是数字") from exc
    if not math.isfinite(x) or not low <= x <= high:
        raise LabError(f"{name} 需在 [{low:g}, {high:g}]")
    return x


def int_opt(value: str | int, name: str, low: int, high: int) -> int:
    try:
        x = int(str(value))
    except (ValueError, TypeError, OverflowError) as exc:
        raise LabError(f"{name} 必须是整数") from exc
    if not low <= x <= high:
        raise LabError(f"{name} 需在 [{low}, {high}]")
    return x


def numbers(value: str, name: str, *, low=1, high=12) -> list[float]:
    try:
        result = [float(x.strip()) for x in str(value).replace(" ", ",").split(",") if x.strip()]
    except ValueError as exc:
        raise LabError(f"{name} 需要逗号分隔的数字") from exc
    if not low <= len(result) <= high or not all(math.isfinite(x) and abs(x) <= 1e8 for x in result):
        raise LabError(f"{name} 需包含 {low}..{high} 个有限数字（绝对值 <=1e8）")
    return result


def options(tokens: list[str], allowed: set[str]) -> tuple[list[str], dict[str, str]]:
    """Parse '--name value' options plus optional non-option positional tokens."""
    pos, opts = [], {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            name = token[2:].lower()
            if name not in allowed:
                raise LabError(f"未知选项 {token}；允许 " + ", ".join("--" + s for s in sorted(allowed)))
            if name in opts or i + 1 >= len(tokens) or tokens[i+1].startswith("--"):
                raise LabError(f"选项 {token} 缺少值或重复")
            opts[name] = tokens[i + 1]
            i += 2
        else:
            pos.append(token)
            i += 1
    return pos, opts
