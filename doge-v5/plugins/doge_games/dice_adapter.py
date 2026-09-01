from __future__ import annotations

from .vendor.dnddice_upstream.dice_parser import DiceParseError, parse
from .vendor.dnddice_upstream.dice_roller import DiceRollError, roll
from .vendor.dnddice_upstream.formatter import format_result


def tabletop_roll(expression: str) -> str:
    raw = (expression or "").strip() or "d20"
    try:
        parsed = parse(raw, default_sides=20, max_input_len=200)
        result = roll(
            parsed,
            max_dice=100,
            max_sides=1000,
            exploding_depth=20,
            reroll_max_depth=20,
            max_total_rolled=500,
        )
        return format_result(result, show_detail=True)
    except (DiceParseError, DiceRollError) as exc:
        raise ValueError(str(exc)) from exc
