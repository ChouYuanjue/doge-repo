import io
import os
import re
import random
import tempfile
from typing import List, Tuple, Set, Optional

from PIL import Image, ImageDraw

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 配置
DEFAULT_W, DEFAULT_H = 20, 20
MIN_W, MIN_H = 10, 10
MAX_W, MAX_H = 50, 50

DEFAULT_RULE = "B3/S23"
DEFAULT_FRAMES = 30
MIN_FRAMES, MAX_FRAMES = 5, 100
DEFAULT_INTERVAL_MS = 200

MAX_PX = 800

# 预配置，左上角为(0,0)
PRESETS = {
    "glider": {(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)},
    "pulsar": {
        (2, 0), (3, 0), (4, 0), (8, 0), (9, 0), (10, 0),
        (0, 2), (5, 2), (7, 2), (12, 2),
        (0, 3), (5, 3), (7, 3), (12, 3),
        (0, 4), (5, 4), (7, 4), (12, 4),
        (2, 5), (3, 5), (4, 5), (8, 5), (9, 5), (10, 5),
        (2, 7), (3, 7), (4, 7), (8, 7), (9, 7), (10, 7),
        (0, 8), (5, 8), (7, 8), (12, 8),
        (0, 9), (5, 9), (7, 9), (12, 9),
        (0, 10), (5, 10), (7, 10), (12, 10),
        (2, 12), (3, 12), (4, 12), (8, 12), (9, 12), (10, 12),
    },
    "lwss": {(1,0),(4,0),(0,1),(0,2),(4,2),(0,3),(1,3),(2,3),(3,3)},
}

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def parse_rule(rule_text: str) -> Tuple[Set[int], Set[int]]:
    # 规则，即birth_set和survive_set
    txt = rule_text.strip().upper().replace(" ", "")
    m = re.fullmatch(r"B([0-8]*)/S([0-8]*)", txt)
    if not m:
        raise ValueError("规则格式应为 B*/S*，例如 B3/S23")
    b = {int(c) for c in m.group(1)} if m.group(1) else set()
    s = {int(c) for c in m.group(2)} if m.group(2) else set()
    return b, s

def empty_grid(w: int, h: int) -> List[List[int]]:
    return [[0]*w for _ in range(h)]

def random_grid(w: int, h: int, density: float = 0.25) -> List[List[int]]:
    g = empty_grid(w, h)
    for y in range(h):
        for x in range(w):
            g[y][x] = 1 if random.random() < density else 0
    return g

def set_cells(grid: List[List[int]], coords: Set[Tuple[int,int]]):
    h = len(grid); w = len(grid[0])
    for (x, y) in coords:
        if 0 <= x < w and 0 <= y < h:
            grid[y][x] = 1

def step(grid: List[List[int]], birth: Set[int], survive: Set[int]) -> List[List[int]]:
    h = len(grid); w = len(grid[0])
    ng = empty_grid(w, h)
    for y in range(h):
        for x in range(w):
            cnt = 0
            #边界之外视为死亡
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        cnt += grid[ny][nx]
            if grid[y][x] == 1:
                ng[y][x] = 1 if cnt in survive else 0
            else:
                ng[y][x] = 1 if cnt in birth else 0
    return ng

def render_frame(grid: List[List[int]]) -> Image.Image:
    h = len(grid); w = len(grid[0])
    cell = max(4, min(20, MAX_PX // max(w, h)))
    img = Image.new("RGB", (w*cell, h*cell), "white")  
    draw = ImageDraw.Draw(img)
    # 画活细胞
    for y in range(h):
        row = grid[y]
        for x in range(w):
            if row[x]:
                x0, y0 = x*cell, y*cell
                draw.rectangle((x0, y0, x0+cell-1, y0+cell-1), fill="black")
    return img

def parse_coords(text: str) -> Set[Tuple[int,int]]:
    """
    支持多种宽松格式坐标：
      "1,2 2,2 3,2"
      "(1,2) (2,2) (3,2)"
      "1 2; 2 2; 3 2"
    """
    s = text.strip()
    s = re.sub(r"[()\[\]]", " ", s)
    toks = re.split(r"[;\s]+", s)
    nums = [t for t in toks if t != ""]
    coords = set()
    i = 0
    while i + 1 < len(nums):
        try:
            x = int(nums[i].rstrip(","))
            y = int(nums[i+1].rstrip(","))
            coords.add((x, y))
        except Exception:
            pass
        i += 2
    return coords

def parse_rle(rle_text: str) -> Tuple[Set[Tuple[int,int]], Optional[str], Optional[Tuple[int,int]]]:
    # 解析 RLE，允许 header
    lines = [ln.strip() for ln in rle_text.strip().splitlines() if ln.strip() and not ln.strip().startswith("#")]
    header_rule = None
    size = None
    # 解析 header
    if lines and ("x" in lines[0] or "y" in lines[0]):
        hdr = lines.pop(0)
        m = re.findall(r"(x|y|rule)\s*=\s*([^,]+)", hdr, flags=re.I)
        kv = {k.lower(): v.strip() for (k, v) in m}
        try:
            w = int(re.sub(r"\D", "", kv.get("x", "")))
            h = int(re.sub(r"\D", "", kv.get("y", "")))
            size = (w, h)
        except Exception:
            pass
        if "rule" in kv:
            header_rule = kv["rule"].upper().replace(" ", "")
    body = "".join(lines)
    i = 0
    run = 0
    x = 0
    y = 0
    cells = set()
    while i < len(body):
        ch = body[i]
        if ch.isdigit():
            run = run * 10 + int(ch)
        elif ch in ("b", "o", "$", "!"):
            n = run if run > 0 else 1
            if ch == "b":
                x += n
            elif ch == "o":
                for _ in range(n):
                    cells.add((x, y))
                    x += 1
            elif ch == "$":
                y += n
                x = 0
            elif ch == "!":
                break
            run = 0
        i += 1
    return cells, header_rule, size

@register("gol", "runnel", "在聊天中生成康威生命游戏GIF", "1.0.0")
class GameOfLifePlugin(Star):
    
    def __init__(self, context: Context):
        super().__init__(context)
        # 每用户状态
        self.sessions = {}  # user_id -> dict(grid, w, h, rule_str, birth, survive, busy, cancel, interval)

  
    def _uid(self, event: AstrMessageEvent) -> str:
        
        try:
            return f"{event.get_sender_id()}@{event.platform}"
        except Exception:
            return str(id(event))

    def _get_or_init(self, uid: str):
        if uid not in self.sessions:
            b, s = parse_rule(DEFAULT_RULE)
            self.sessions[uid] = {
                "w": DEFAULT_W, "h": DEFAULT_H,
                "rule_str": DEFAULT_RULE, "birth": b, "survive": s,
                "grid": random_grid(DEFAULT_W, DEFAULT_H, 0.25),
                "busy": False, "cancel": False,
                "interval": DEFAULT_INTERVAL_MS,
            }
        return self.sessions[uid]

    def _set_rule(self, sess, rule_str: str):
        b, s = parse_rule(rule_str)
        sess["rule_str"] = rule_str.upper()
        sess["birth"] = b
        sess["survive"] = s

    def _set_size(self, sess, w: int, h: int):
        w = clamp(w, MIN_W, MAX_W)
        h = clamp(h, MIN_H, MAX_H)
        sess["w"] = w; sess["h"] = h
        sess["grid"] = random_grid(w, h, 0.25)

    
    @filter.command("gol")
    async def gol_dispatch(self, event: AstrMessageEvent):
        msg = (event.message_str or "").strip()
        
        parts = msg.split(" ", 2)
        if len(parts) == 1:
            yield event.plain_result("用法: /gol <start|rule|frame|load|stop|size> ")
            return
        sub = parts[1].lower()
        arg = parts[2] if len(parts) >= 3 else ""

        if sub == "start":
            async for res in self._cmd_start(event, arg):
                yield res
        elif sub == "rule":
            async for res in self._cmd_rule(event, arg):
                yield res
        elif sub == "frame":
            async for res in self._cmd_frame(event, arg):
                yield res
        elif sub == "load":
            async for res in self._cmd_load(event, arg):
                yield res
        elif sub == "stop":
            async for res in self._cmd_stop(event):
                yield res
        elif sub == "size":
            async for res in self._cmd_size(event, arg):
                yield res
        else:
            yield event.plain_result("未知子命令。可用: start, rule, frame, load, stop, size")

    async def _cmd_start(self, event: AstrMessageEvent, payload: str):
        uid = self._uid(event)
        sess = self._get_or_init(uid)
        if sess["busy"]:
            yield event.plain_result("当前已有生成任务在进行中，请先 /gol stop 或等待完成。")
            return

        payload = payload.strip()
        if not payload:
            yield event.plain_result("用法: /gol start <RLE|坐标列表>")
            return

        # 尝试 RLE 解析；如果失败再尝试坐标
        try:
            cells, r_rule, r_size = parse_rle(payload)
            if r_rule:
                self._set_rule(sess, r_rule)
            w, h = sess["w"], sess["h"]
            if r_size:
                w = clamp(r_size[0], MIN_W, MAX_W)
                h = clamp(r_size[1], MIN_H, MAX_H)
                sess["w"], sess["h"] = w, h
            grid = empty_grid(w, h)
            set_cells(grid, cells)
            sess["grid"] = grid
            yield event.plain_result(f"RLE 初态已载入，规则 {sess['rule_str']}，网格 {w}x{h}。")
            return
        except Exception:
            pass

        # 解析坐标
        coords = parse_coords(payload)
        if not coords:
            yield event.plain_result("未能解析输入。请提供有效的 RLE 或坐标列表。")
            return
        w, h = sess["w"], sess["h"]
        grid = empty_grid(w, h)
        set_cells(grid, coords)
        sess["grid"] = grid
        yield event.plain_result(f"坐标初态已载入，规则 {sess['rule_str']}，网格 {w}x{h}。")

    async def _cmd_rule(self, event: AstrMessageEvent, arg: str):
        uid = self._uid(event)
        sess = self._get_or_init(uid)
        if sess["busy"]:
            yield event.plain_result("当前已有生成任务在进行中，请先 /gol stop 或等待完成。")
            return
        arg = arg.strip()
        if not arg:
            yield event.plain_result("用法: /gol rule <B*/S*>，例如 /gol rule B3/S23")
            return
        try:
            self._set_rule(sess, arg)
        except Exception as e:
            yield event.plain_result(f"规则无效：{e}")
            return
        # 随机初态
        sess["grid"] = random_grid(sess["w"], sess["h"], 0.25)
        yield event.plain_result(f"已设置规则为 {sess['rule_str']}，并随机生成初态。")

    async def _cmd_frame(self, event: AstrMessageEvent, arg: str):
        uid = self._uid(event)
        sess = self._get_or_init(uid)
        if sess["busy"]:
            yield event.plain_result("当前已有生成任务在进行中，请先 /gol stop 或等待完成。")
            return

        arg = arg.strip()
        steps = DEFAULT_FRAMES
        if arg:
            m = re.match(r"\d+", arg)
            if m:
                steps = int(m.group(0))
        steps = clamp(steps, MIN_FRAMES, MAX_FRAMES)

        sess["busy"] = True
        sess["cancel"] = False

        try:
            grid = [row[:] for row in sess["grid"]]  
            b, s = sess["birth"], sess["survive"]
            frames: List[Image.Image] = []

            for i in range(steps):
                if sess["cancel"]:
                    yield event.plain_result("已终止当前生成任务。")
                    break
                frames.append(render_frame(grid))
                grid = step(grid, b, s)

            if frames and not sess["cancel"]:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".gif") as tmp:
                    tmp_path = tmp.name
                try:
                    frames[0].save(
                        tmp_path,
                        save_all=True,
                        append_images=frames[1:],
                        format="GIF",
                        duration=sess["interval"],  
                        loop=0,
                        disposal=2,
                        optimize=False,
                    )
                    yield event.image_result(tmp_path)
                finally:
                    
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

            if not sess["cancel"]:
                sess["grid"] = grid

        except Exception as e:
            logger.error(f"/gol frame 失败: {e}", exc_info=True)
            yield event.plain_result(f"生成失败：{e}")
        finally:
            sess["busy"] = False
            sess["cancel"] = False

    async def _cmd_load(self, event: AstrMessageEvent, arg: str):
        uid = self._uid(event)
        sess = self._get_or_init(uid)
        if sess["busy"]:
            yield event.plain_result("当前已有生成任务在进行中，请先 /gol stop 或等待完成。")
            return
        name = arg.strip().lower()
        if name not in PRESETS:
            yield event.plain_result(f"未知预设。可用：{', '.join(PRESETS.keys())}")
            return
        w, h = sess["w"], sess["h"]
        grid = empty_grid(w, h)
        set_cells(grid, PRESETS[name])
        sess["grid"] = grid
        yield event.plain_result(f"已载入预设 {name}，网格 {w}x{h}，规则 {sess['rule_str']}。")

    async def _cmd_stop(self, event: AstrMessageEvent):
        uid = self._uid(event)
        sess = self._get_or_init(uid)
        if not sess["busy"]:
            yield event.plain_result("当前没有正在执行的生成任务。")
            return
        sess["cancel"] = True
        yield event.plain_result("已请求终止当前生成任务。")

    async def _cmd_size(self, event: AstrMessageEvent, arg: str):
        uid = self._uid(event)
        sess = self._get_or_init(uid)
        if sess["busy"]:
            yield event.plain_result("当前已有生成任务在进行中，请先 /gol stop 或等待完成。")
            return
        a = arg.strip().lower().replace("×", "x")
        m = re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", a)
        if not m:
            yield event.plain_result("用法：/gol size <WxH>，例如 /gol size 20x20")
            return
        w = int(m.group(1)); h = int(m.group(2))
        self._set_size(sess, w, h)
        yield event.plain_result(f"已设置网格为 {sess['w']}x{sess['h']}，并随机生成初态。")
