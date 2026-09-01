from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from .vendor.minesweeper_upstream.core.game import MineSweeper
from .vendor.minesweeper_upstream.core.model import GameSpec, GameState
from .vendor.minesweeper_upstream.core.renderer import MineSweeperRenderer
from .vendor.minesweeper_upstream.core.skin import SkinManager

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor" / "minesweeper_upstream"
LEVELS = {
    "easy": GameSpec(9, 9, 10),
    "normal": GameSpec(16, 16, 40),
    "hard": GameSpec(16, 30, 99),
}
_COORD = re.compile(r"^([A-Za-z])(\d{1,2})$")


def parse_coord(token: str, rows: int, cols: int) -> tuple[int, int]:
    m = _COORD.fullmatch(token.strip())
    if not m:
        raise ValueError(f"坐标格式错误：{token}；示例 A1")
    row = ord(m.group(1).upper()) - 65
    col = int(m.group(2)) - 1
    if not (0 <= row < rows and 0 <= col < cols):
        raise ValueError(f"坐标超出棋盘：{token}")
    return row, col


async def new_game(level: str = "normal") -> MineSweeper:
    level = level.lower()
    if level not in LEVELS:
        raise ValueError("扫雷难度只能是 easy / normal / hard")
    spec = LEVELS[level]
    mgr = SkinManager(SimpleNamespace(skins_dir=VENDOR / "skins"))
    await mgr.initialize()
    if not mgr.skin_list:
        raise RuntimeError("扫雷皮肤资源缺失")
    skin_name = "winxp" if "winxp" in mgr.skin_list else mgr.skin_list[0]
    skin = mgr.load(skin_name, spec)
    renderer = MineSweeperRenderer(spec, skin, str(VENDOR / "font.ttf"), scale=3)
    return MineSweeper(spec, renderer, display_name=level)


def apply(game: MineSweeper, action: str, coords: list[str]) -> str:
    if action not in {"open", "mark", "sweep"}:
        raise ValueError("扫雷操作只能是 open / mark / sweep")
    if not coords:
        raise ValueError(f"用法：/game mine {action} A1 [B2 ...]")
    messages: list[str] = []
    for token in coords[:20]:
        x, y = parse_coord(token, game.spec.rows, game.spec.cols)
        result = game.open(x, y) if action == "open" else game.mark(x, y) if action == "mark" else game.sweep(x, y)
        if result is not None:
            messages.append(f"{token.upper()}: {result.name.lower()}")
        if game.is_over:
            break
    if game.state == GameState.WIN:
        messages.append("完成：全部安全格已打开。")
    elif game.state == GameState.FAIL:
        messages.append("踩雷，本局结束。")
    return " · ".join(messages) if messages else "棋盘已更新。"


def render(game: MineSweeper, output_dir: Path, scope_key: str) -> Path:
    out = Path(output_dir) / "mine"
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", scope_key)[-80:] or "session"
    p = out / f"{safe}.png"
    p.write_bytes(game.draw())
    return p
