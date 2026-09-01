from __future__ import annotations

from dataclasses import dataclass, field

RINGS = ("A", "B", "C")
POSITIONS = tuple(f"{ring}{i}" for ring in RINGS for i in range(1, 9))
MILLS = tuple(
    tuple(f"{ring}{i}" for i in triple)
    for ring in RINGS
    for triple in ((1, 2, 3), (3, 4, 5), (5, 6, 7), (7, 8, 1))
) + (
    ("A2", "B2", "C2"),
    ("A4", "B4", "C4"),
    ("A6", "B6", "C6"),
    ("A8", "B8", "C8"),
)


def _build_adjacency() -> dict[str, set[str]]:
    result = {p: set() for p in POSITIONS}
    for ring in RINGS:
        for i in range(1, 9):
            p = f"{ring}{i}"
            result[p].add(f"{ring}{8 if i == 1 else i - 1}")
            result[p].add(f"{ring}{1 if i == 8 else i + 1}")
    for i in (2, 4, 6, 8):
        result[f"A{i}"].add(f"B{i}")
        result[f"B{i}"].update({f"A{i}", f"C{i}"})
        result[f"C{i}"].add(f"B{i}")
    return result


ADJACENCY = _build_adjacency()


def normalize_pos(value: str) -> str:
    pos = value.strip().upper()
    if pos not in POSITIONS:
        raise ValueError("位置必须是 A1-A8、B1-B8 或 C1-C8")
    return pos


@dataclass
class MorrisGame:
    players: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    board: dict[str, int] = field(default_factory=dict)
    to_place: list[int] = field(default_factory=lambda: [9, 9])
    turn: int = 0
    capture_by: int | None = None
    winner: int | None = None

    def add_player(self, user_id: str, name: str = "") -> int:
        uid = str(user_id)
        if uid in self.players:
            return self.players.index(uid)
        if len(self.players) >= 2:
            raise ValueError("本局已经有两位玩家")
        self.players.append(uid)
        self.names.append(name or uid)
        return len(self.players) - 1

    @property
    def ready(self) -> bool:
        return len(self.players) == 2

    @property
    def stage(self) -> str:
        return "placement" if any(self.to_place) else "movement"

    def pieces(self, player: int) -> set[str]:
        return {p for p, owner in self.board.items() if owner == player}

    def in_mill(self, pos: str, player: int) -> bool:
        return any(pos in mill and all(self.board.get(x) == player for x in mill) for mill in MILLS)

    def _player(self, user_id: str) -> int:
        if self.winner is not None:
            raise ValueError("本局已经结束")
        if not self.ready:
            raise ValueError("还需要第二位玩家：/game nc join")
        uid = str(user_id)
        if uid not in self.players:
            raise ValueError("你不是本局玩家")
        player = self.players.index(uid)
        expected = self.capture_by if self.capture_by is not None else self.turn
        if player != expected:
            raise ValueError("还没轮到你")
        return player

    def _finish_turn(self, player: int) -> None:
        opponent = 1 - player
        if self.stage == "movement":
            if len(self.pieces(opponent)) < 3 or not self.has_legal_move(opponent):
                self.winner = player
                return
        self.turn = opponent

    def act(self, user_id: str, action: str) -> str:
        player = self._player(user_id)
        action = action.strip().upper()
        if self.capture_by is not None:
            if action.startswith("X"):
                action = action[1:].strip()
            return self.capture(user_id, action)

        if self.stage == "placement":
            pos = normalize_pos(action)
            if pos in self.board:
                raise ValueError("该位置已有棋子")
            self.board[pos] = player
            self.to_place[player] -= 1
            if self.in_mill(pos, player):
                self.capture_by = player
                return f"{self.names[player]} 形成磨坊，请用 /game nc x <位置> 移除对方一子。"
            self._finish_turn(player)
            return "落子成功。"

        if "-" not in action:
            raise ValueError("移动阶段请使用 A1-A2 形式")
        source, target = (normalize_pos(x) for x in action.split("-", 1))
        if self.board.get(source) != player:
            raise ValueError("起点不是你的棋子")
        if target in self.board:
            raise ValueError("目标位置已有棋子")
        if len(self.pieces(player)) != 3 and target not in ADJACENCY[source]:
            raise ValueError("只能沿连线移动到相邻空位；仅剩 3 子时可以飞行")
        del self.board[source]
        self.board[target] = player
        if self.in_mill(target, player):
            self.capture_by = player
            return f"{self.names[player]} 形成磨坊，请用 /game nc x <位置> 移除对方一子。"
        self._finish_turn(player)
        return "移动成功。"

    def capture(self, user_id: str, target: str) -> str:
        player = self._player(user_id)
        if self.capture_by != player:
            raise ValueError("当前不能移除棋子")
        target = normalize_pos(target)
        opponent = 1 - player
        if self.board.get(target) != opponent:
            raise ValueError("这里只能移除对方棋子")
        pieces = self.pieces(opponent)
        non_mill = {p for p in pieces if not self.in_mill(p, opponent)}
        if target not in (non_mill or pieces):
            raise ValueError("对方还有不在磨坊中的棋子，不能先拆磨坊")
        del self.board[target]
        self.capture_by = None
        self._finish_turn(player)
        return f"{self.names[player]} 获胜。" if self.winner == player else "已移除对方棋子。"

    def has_legal_move(self, player: int) -> bool:
        pieces = self.pieces(player)
        empties = set(POSITIONS) - set(self.board)
        if len(pieces) == 3:
            return bool(empties)
        return any(ADJACENCY[p] & empties for p in pieces)

    def render(self) -> str:
        def node(pos: str) -> str:
            owner = self.board.get(pos)
            return pos if owner is None else ("● " if owner == 0 else "○ ")

        lines = [
            f"{node('A1')}-----------{node('A2')}-----------{node('A3')}",
            "|             |             |",
            f"|   {node('B1')}-------{node('B2')}-------{node('B3')}   |",
            "|   |         |         |   |",
            f"|   |   {node('C1')}---{node('C2')}---{node('C3')}   |   |",
            f"{node('A8')}--{node('B8')}--{node('C8')}       {node('C4')}--{node('B4')}--{node('A4')}",
            f"|   |   {node('C7')}---{node('C6')}---{node('C5')}   |   |",
            "|   |         |         |   |",
            f"|   {node('B7')}-------{node('B6')}-------{node('B5')}   |",
            "|             |             |",
            f"{node('A7')}-----------{node('A6')}-----------{node('A5')}",
        ]
        p0 = self.names[0] if self.names else "玩家1"
        p1 = self.names[1] if len(self.names) > 1 else "等待加入"
        footer = f"● {p0}  ○ {p1}  阶段: {self.stage}"
        if self.winner is not None:
            footer += f"  胜者: {self.names[self.winner]}"
        elif self.capture_by is not None:
            footer += f"  等待 {self.names[self.capture_by]} 移除棋子"
        elif self.ready:
            footer += f"  轮到: {self.names[self.turn]}"
        return "\n".join(lines + [footer])
