from __future__ import annotations

import asyncio

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.game24 import check as check_24, new_round as new_24_round
from data.plugins.doge_shared.morris import MorrisGame
from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.signal import new_game as new_signal_game

from .dice_adapter import tabletop_roll
from .minesweeper_adapter import apply as mine_apply
from .minesweeper_adapter import new_game as new_mine_game
from .minesweeper_adapter import render as render_mine
from .sudoku_adapter import new_game as new_sudoku
from .sudoku_adapter import render as render_sudoku


@register("doge_games", "runnel", "Doge 群聊游戏、解谜与桌面骰池", "5.5.0")
class DogeGames(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("doge_games")
        self._round24: dict[str, dict] = {}
        self._morris: dict[str, MorrisGame] = {}
        self._signals = {}
        self._mines = {}
        self._sudoku = {}

    @filter.command("game")
    async def game_command(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "game")
            parts = split_head(payload, 1)
            if not parts:
                yield text_result(
                    event,
                    "**Doge Game**\n\n"
                    "- `/game 24 [new|wild|reveal|<expression>]`\n"
                    "- `/game nc start|join|board|end|A1|A1-A2|x A1`\n"
                    "- `/game signal new [easy|normal|hard]` · `hint` · `show` · `solve <答案>`\n"
                    "- `/game mine [easy|normal|hard]` · `open A1` · `mark A1` · `sweep A1` · `board|end`\n"
                    "- `/game sudoku [easy|normal|hard]` · `A1 5` · `show|reveal|end`\n"
                    "- `/game dice <Roll20 风格骰池>`，如 `d20adv`、`4d6kh3`、`d6!`",
                )
                return
            kind = parts[0].lower()
            rest = parts[1].strip() if len(parts) > 1 else ""
            scope = event.unified_msg_origin
            uid = str(event.get_sender_id())
            name = event.get_sender_name() or uid

            if kind in {"dice", "roll"}:
                yield text_result(event, tabletop_roll(rest), markdown=False)
                return

            if kind in {"mine", "minesweeper"}:
                tokens = rest.split()
                action = tokens[0].lower() if tokens else "normal"
                if action in {"easy", "normal", "hard", "new", "start"}:
                    level = action if action in {"easy", "normal", "hard"} else (tokens[1].lower() if len(tokens) > 1 else "normal")
                    game = await new_mine_game(level)
                    self._mines[scope] = game
                    path = render_mine(game, self.data_dir, scope)
                    yield image_result(event, path, f"扫雷 {level} · 首次落点保证安全 · /game mine open A1")
                    return
                game = self._mines.get(scope)
                if not game:
                    raise ValueError("当前没有扫雷。用 /game mine easy|normal|hard 开局")
                if action in {"board", "show", "status"}:
                    path = render_mine(game, self.data_dir, scope)
                    yield image_result(event, path, "扫雷当前棋盘")
                    return
                if action in {"end", "stop", "quit"}:
                    self._mines.pop(scope, None)
                    yield text_result(event, "扫雷已结束。", markdown=False)
                    return
                coords = tokens[1:]
                if action not in {"open", "mark", "sweep"}:
                    # 允许 /game mine A1 B2 作为 open 的短写。
                    coords = tokens
                    action = "open"
                message = mine_apply(game, action, coords)
                path = render_mine(game, self.data_dir, scope)
                if game.is_over:
                    self._mines.pop(scope, None)
                yield image_result(event, path, message)
                return

            if kind in {"sudoku", "sdk"}:
                tokens = rest.split()
                action = tokens[0].lower() if tokens else "normal"
                if action in {"easy", "normal", "hard", "new", "start"}:
                    level = action if action in {"easy", "normal", "hard"} else (tokens[1].lower() if len(tokens) > 1 else "normal")
                    game = await asyncio.to_thread(new_sudoku, level)
                    self._sudoku[scope] = game
                    path = render_sudoku(game, self.data_dir, scope)
                    yield image_result(event, path, f"唯一解数独 {level} · 3 lives · /game sudoku A1 5")
                    return
                game = self._sudoku.get(scope)
                if not game:
                    raise ValueError("当前没有数独。用 /game sudoku easy|normal|hard 开局")
                if action in {"show", "board", "status"}:
                    path = render_sudoku(game, self.data_dir, scope)
                    yield image_result(event, path, f"数独 {game.difficulty} · lives={game.lives}")
                    return
                if action in {"reveal", "answer"}:
                    path = render_sudoku(game, self.data_dir, scope, reveal=True)
                    self._sudoku.pop(scope, None)
                    yield image_result(event, path, "数独答案，本局结束。")
                    return
                if action in {"end", "stop", "quit"}:
                    self._sudoku.pop(scope, None)
                    yield text_result(event, "数独已结束。", markdown=False)
                    return
                if action in {"set", "fill"}:
                    if len(tokens) < 3:
                        raise ValueError("用法：/game sudoku set A1 5")
                    coord, raw_value = tokens[1], tokens[2]
                else:
                    if len(tokens) < 2:
                        raise ValueError("用法：/game sudoku A1 5")
                    coord, raw_value = tokens[0], tokens[1]
                message = game.set_cell(coord, int(raw_value))
                reveal = game.lives <= 0
                if game.complete:
                    message += " · 完成！"
                elif reveal:
                    message += " · 机会用尽，显示答案。"
                path = render_sudoku(game, self.data_dir, scope, reveal=reveal)
                if game.complete or reveal:
                    self._sudoku.pop(scope, None)
                yield image_result(event, path, message)
                return

            if kind in {"24", "24p", "point24"}:
                action = rest.lower()
                if not rest or action in {"new", "start", "wild"}:
                    nums, solution = new_24_round()
                    wild = action == "wild"
                    self._round24[scope] = {"numbers": nums, "solution": solution, "wild": wild}
                    tag = " · wild：额外允许 << >> & | ^" if wild else ""
                    yield text_result(
                        event,
                        f"24 点{tag}\n{'  '.join(map(str, nums))}\n"
                        "只可各用一次这四个数字；直接回复 `/game 24 <表达式>`",
                    )
                    return
                game = self._round24.get(scope)
                if not game:
                    yield text_result(event, "当前没有 24 点题目。用 `/game 24 new` 或 `/game 24 wild` 开一局。")
                    return
                if action in {"reveal", "answer", "ans"}:
                    self._round24.pop(scope, None)
                    yield text_result(event, f"答案之一：`{game['solution']} = 24`")
                    return
                value = check_24(rest, game["numbers"], wild=bool(game["wild"]))
                if value == 24:
                    self._round24.pop(scope, None)
                    yield text_result(event, f"✓ `{rest} = 24`。")
                else:
                    yield text_result(event, f"这个表达式 = `{value}`，还不是 24。")
                return

            if kind in {"nc", "morris", "nine"}:
                action = rest.strip()
                lower = action.lower()
                if lower in {"help", "?"} or not action:
                    yield text_result(
                        event,
                        "Nine Men's Morris / 九子棋\n"
                        "`/game nc start` 开局 · `join` 加入 · `board` 看棋盘 · `end` 结束\n"
                        "放置：`/game nc A1` · 移动：`/game nc A1-A2` · 成磨坊后吃子：`/game nc x B4`",
                        markdown=False,
                    )
                    return
                if lower in {"start", "new"}:
                    old_game = self._morris.get(scope)
                    if old_game and old_game.winner is None:
                        raise ValueError("本会话已经有一局九子棋；先 /game nc end")
                    game = MorrisGame()
                    game.add_player(uid, name)
                    self._morris[scope] = game
                    yield text_result(event, "九子棋已创建，等待第二位玩家 /game nc join\n" + game.render(), markdown=False)
                    return
                game = self._morris.get(scope)
                if not game:
                    raise ValueError("当前没有九子棋。用 /game nc start 开局")
                if lower == "join":
                    game.add_player(uid, name)
                    yield text_result(event, "加入成功。\n" + game.render(), markdown=False)
                    return
                if lower in {"board", "status"}:
                    yield text_result(event, game.render(), markdown=False)
                    return
                if lower in {"end", "stop"}:
                    if uid not in game.players:
                        raise ValueError("只有本局玩家可以结束九子棋")
                    self._morris.pop(scope, None)
                    yield text_result(event, "九子棋已结束。", markdown=False)
                    return
                result = game.act(uid, action)
                board = game.render()
                if game.winner is not None:
                    self._morris.pop(scope, None)
                yield text_result(event, result + "\n" + board, markdown=False)
                return

            if kind in {"signal", "sig"}:
                p = split_head(rest, 1)
                action = p[0].lower() if p else "new"
                tail = p[1] if len(p) > 1 else ""
                if action in {"new", "start"}:
                    difficulty = tail.strip().lower() or "normal"
                    if difficulty not in {"easy", "normal", "hard"}:
                        raise ValueError("难度只能是 easy / normal / hard")
                    game = new_signal_game(difficulty)
                    self._signals[scope] = game
                    yield text_result(
                        event,
                        f"📡 捕获到一段 {difficulty} 信号：\n`{game.encoded}`\n\n线索：{game.first_clue()}\n"
                        "使用 `/game signal hint` 获取下一层提示；`/game signal solve <答案>` 解码。",
                    )
                    return
                game = self._signals.get(scope)
                if not game:
                    yield text_result(event, "当前没有活动信号。使用 `/game signal new [easy|normal|hard]`。")
                    return
                if action == "hint":
                    yield text_result(
                        event,
                        "每一层编码类型都已经暴露了，剩下只能亲自拆。"
                        if game.hints_used >= len(game.layers) - 1
                        else game.hint(),
                    )
                    return
                if action in {"show", "status"}:
                    yield text_result(event, f"📡 当前信号：\n`{game.encoded}`\n\n{game.first_clue()}")
                    return
                if action == "solve":
                    if not tail.strip():
                        raise ValueError("用法：/game signal solve <完整答案>")
                    if game.check(tail):
                        score = game.score()
                        self._signals.pop(scope, None)
                        yield text_result(event, f"✅ 信号解码成功：{game.answer}\n得分：**{score}/100**")
                    else:
                        yield text_result(event, "❌ 对不上这条信号。答案需要是完整原句。")
                    return
                raise ValueError("用法：/game signal new|hint|show|solve")

            raise ValueError(f"未知 game 类型：{kind}。支持 24 / nc / signal / mine / sudoku / dice")
        except Exception as exc:
            yield text_result(event, f"game 失败：{exc}", markdown=False)
