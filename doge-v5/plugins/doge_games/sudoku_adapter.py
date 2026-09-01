from __future__ import annotations

import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VENDOR = Path(__file__).resolve().parent / "vendor" / "pysudoku_upstream"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))
from sudoku import Sudoku  # type: ignore  # pinned upstream expects top-level package import

LEVELS = {"easy": 42, "normal": 36, "hard": 30}  # target clue counts
_COORD = re.compile(r"^([A-Za-z])(\d{1,2})$")


def parse_coord(token: str) -> tuple[int, int]:
    m = _COORD.fullmatch(token.strip())
    if not m:
        raise ValueError(f"坐标格式错误：{token}；示例 A1")
    row = ord(m.group(1).upper()) - 65
    col = int(m.group(2)) - 1
    if not (0 <= row < 9 and 0 <= col < 9):
        raise ValueError(f"坐标超出数独棋盘：{token}")
    return row, col


@dataclass
class SudokuSession:
    puzzle: list[list[int | None]]
    solution: list[list[int]]
    board: list[list[int | None]]
    difficulty: str
    lives: int = 3
    started_at: float = 0.0

    def __post_init__(self):
        if not self.started_at:
            self.started_at = time.time()

    @property
    def complete(self) -> bool:
        return all(self.board[r][c] == self.solution[r][c] for r in range(9) for c in range(9))

    def set_cell(self, coord: str, value: int) -> str:
        r, c = parse_coord(coord)
        if not 1 <= value <= 9:
            raise ValueError("数独填入值必须是 1-9")
        if self.puzzle[r][c] not in (None, 0):
            raise ValueError(f"{coord.upper()} 是题目给定格，不能修改")
        if value != self.solution[r][c]:
            self.lives -= 1
            return f"{coord.upper()}={value} 不对；剩余 {self.lives} 次机会"
        self.board[r][c] = value
        return f"{coord.upper()}={value} ✓"


def new_game(level: str = "normal") -> SudokuSession:
    level = level.lower()
    if level not in LEVELS:
        raise ValueError("数独难度只能是 easy / normal / hard")
    target_clues = LEVELS[level]

    # Start from a complete grid, then remove clues only when the pinned
    # py-sudoku solver confirms uniqueness is preserved.  This is both faster
    # and much more reliable than asking `.difficulty()` to randomly remove a
    # fixed percentage and hoping the resulting puzzle is unique.
    solved = Sudoku(3).solve(assert_solvable=True)
    if solved is None:
        raise RuntimeError("数独完整盘生成失败")
    solution = [[int(cell) for cell in row] for row in solved.board]
    pboard: list[list[int | None]] = [row[:] for row in solution]
    cells = list(range(81))
    random.SystemRandom().shuffle(cells)
    clues = 81
    for idx in cells:
        if clues <= target_clues:
            break
        r, c = divmod(idx, 9)
        old = pboard[r][c]
        pboard[r][c] = None
        candidate = Sudoku(3, 3, board=[row[:] for row in pboard])
        if candidate.has_multiple_solutions():
            pboard[r][c] = old
        else:
            clues -= 1
    if clues > target_clues:
        raise RuntimeError(f"唯一解数独生成只降到 {clues} clues，请重试")
    return SudokuSession(
        puzzle=[row[:] for row in pboard],
        solution=solution,
        board=[row[:] for row in pboard],
        difficulty=level,
    )


def _font(size: int):
    for p in (
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/google-noto-sans-cjk-ttc/NotoSansCJK-Regular.ttc",
    ):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render(game: SudokuSession, output_dir: Path, scope_key: str, reveal: bool = False) -> Path:
    cell = 58
    pad = 52
    size = pad + cell * 9 + 18
    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    font = _font(31)
    small = _font(19)
    board = game.solution if reveal else game.board
    for i in range(10):
        width = 4 if i % 3 == 0 else 1
        pos = pad + i * cell
        draw.line((pad, pos, pad + 9 * cell, pos), fill="black", width=width)
        draw.line((pos, pad, pos, pad + 9 * cell), fill="black", width=width)
    for i in range(9):
        draw.text((pad + i * cell + cell / 2, 22), str(i + 1), fill="black", font=small, anchor="mm")
        draw.text((24, pad + i * cell + cell / 2), chr(65 + i), fill="black", font=small, anchor="mm")
    for r in range(9):
        for c in range(9):
            value = board[r][c]
            if value in (None, 0):
                continue
            given = game.puzzle[r][c] not in (None, 0)
            fill = "black" if given or reveal else "#375a7f"
            draw.text(
                (pad + c * cell + cell / 2, pad + r * cell + cell / 2),
                str(value), fill=fill, font=font, anchor="mm"
            )
    out = Path(output_dir) / "sudoku"
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", scope_key)[-80:] or "session"
    path = out / f"{safe}.png"
    img.save(path)
    return path
