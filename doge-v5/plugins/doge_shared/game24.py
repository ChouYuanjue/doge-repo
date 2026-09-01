from __future__ import annotations

import ast
import random
from collections import Counter
from fractions import Fraction
from typing import Iterable


def _combine(left: tuple[Fraction, str], right: tuple[Fraction, str]):
    a, ea = left
    b, eb = right
    yield a + b, f"({ea}+{eb})"
    yield a - b, f"({ea}-{eb})"
    yield b - a, f"({eb}-{ea})"
    yield a * b, f"({ea}*{eb})"
    if b:
        yield a / b, f"({ea}/{eb})"
    if a:
        yield b / a, f"({eb}/{ea})"


def solve_24(numbers: Iterable[int]) -> str | None:
    nums = tuple(int(x) for x in numbers)
    if len(nums) != 4:
        raise ValueError("24 点必须恰好使用 4 个数")

    def rec(items: tuple[tuple[Fraction, str], ...]) -> str | None:
        if len(items) == 1:
            return items[0][1] if items[0][0] == 24 else None
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                rest = tuple(items[k] for k in range(len(items)) if k not in (i, j))
                seen: set[Fraction] = set()
                for value, expr in _combine(items[i], items[j]):
                    if value in seen:
                        continue
                    seen.add(value)
                    answer = rec(rest + ((value, expr),))
                    if answer:
                        return answer
        return None

    return rec(tuple((Fraction(n), str(n)) for n in nums))


def new_round(rng: random.Random | None = None) -> tuple[tuple[int, int, int, int], str]:
    rng = rng or random.Random()
    for _ in range(1000):
        nums = tuple(rng.randint(1, 13) for _ in range(4))
        solution = solve_24(nums)
        if solution:
            return nums, solution
    raise RuntimeError("无法生成可解的 24 点题目")


def _used_numbers(tree: ast.AST) -> list[int]:
    values: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool) or int(node.value) != node.value:
                raise ValueError("只允许使用题目给出的整数")
            values.append(int(node.value))
    return values


def _evaluate(node: ast.AST, wild: bool) -> Fraction:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, wild)
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return Fraction(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand, wild)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, wild)
        right = _evaluate(node.right, wild)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ValueError("除数不能为 0")
            return left / right
        if wild:
            if left.denominator != 1 or right.denominator != 1:
                raise ValueError("位运算只能作用于整数")
            a, b = int(left), int(right)
            if isinstance(node.op, ast.LShift):
                return Fraction(a << b)
            if isinstance(node.op, ast.RShift):
                return Fraction(a >> b)
            if isinstance(node.op, ast.BitAnd):
                return Fraction(a & b)
            if isinstance(node.op, ast.BitOr):
                return Fraction(a | b)
            if isinstance(node.op, ast.BitXor):
                return Fraction(a ^ b)
    raise ValueError("只允许括号、四则运算" + ("以及位运算" if wild else ""))


def check(expression: str, numbers: Iterable[int], *, wild: bool = False) -> Fraction:
    nums = tuple(int(n) for n in numbers)
    normalized = (
        expression.replace("（", "(")
        .replace("）", ")")
        .replace("×", "*")
        .replace("÷", "/")
        .replace("＋", "+")
        .replace("－", "-")
    )
    tree = ast.parse(normalized, mode="eval")
    if Counter(_used_numbers(tree)) != Counter(nums):
        raise ValueError(f"必须且只能使用题目中的数字：{' '.join(map(str, nums))}")
    return _evaluate(tree, wild)
