import os
import json
import re
import random
import copy
from PIL import Image, ImageDraw, ImageFont
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("gomoku", "zhx,runnel", "五子棋插件", "1.1.0")
class GomokuPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.games = {}  # 维护游戏会话
        self.board_size = 15
        self.pvp_sessions = {}  # 维护 PVP 模式游戏
        self.current_player = {}  # 记录当前 PVP 游戏的当前玩家
        self.player_names = {}  # 全局存储玩家名字
        self.board_history = {}  # 记录棋盘历史，用于悔棋
        self.last_move_history = {}  # 记录最后一步的位置历史
        self.undo_requests = {}  # 记录悔棋请求

    def get_session_id(self, event: AstrMessageEvent):
        """获取唯一的游戏标识"""
        return event.get_group_id() if event.get_group_id() else event.get_session_id()

    def get_player_id(self, event: AstrMessageEvent):
        """获取玩家的唯一标识"""
        if event.get_group_id():
            return f"{event.get_group_id()}_{event.get_sender_id()}"
        return event.get_session_id()

    def get_player_name(self, player_id: str) -> str:
        """根据玩家ID获取名字"""
        name = self.player_names.get(player_id)
        if not name:
            # 如果没有保存的名字，从ID中提取
            if '_' in player_id:
                # 群聊模式，返回用户ID部分
                return player_id.split('_')[1]
            # 私聊模式，返回完整ID
            return player_id
        return name

    def save_player_name(self, player_id: str, name: str):
        """保存玩家名字"""
        if name:  # 只在名字非空时保存
            self.player_names[player_id] = name

    def create_board(self):
        """创建空棋盘"""
        return [[0] * self.board_size for _ in range(self.board_size)]

    def save_board_state(self, session_id, board, last_move=None):
        """保存当前棋盘状态到历史记录"""
        if session_id not in self.board_history:
            self.board_history[session_id] = []
            self.last_move_history[session_id] = []
        
        # 深拷贝棋盘状态，确保历史记录不会被当前操作影响
        self.board_history[session_id].append(copy.deepcopy(board))
        self.last_move_history[session_id].append(copy.deepcopy(last_move))

    def can_undo(self, session_id):
        """检查是否可以悔棋"""
        return (session_id in self.board_history and 
                len(self.board_history[session_id]) >= 2)  # 至少需要两步才能悔棋

    def draw_board(self, board, last_move=None, session_id=None):
        """绘制棋盘图片并返回路径"""
        cell_size = 40
        margin = 35  # 稍微增加边缘留白，为更大的数字留出空间
        img_size = self.board_size * cell_size + 2 * margin
        img = Image.new("RGB", (img_size, img_size), "#F0D9B5")
        draw = ImageDraw.Draw(img)
        
        font_size = 24  # 定义字体大小
        # 尝试按顺序加载各种Linux常见字体
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "/usr/share/fonts/noto/NotoSans-Regular.ttf"
        ]
        
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, font_size)
                logger.info(f"成功加载字体: {path}")
                break
            except:
                continue
                
        if font is None:
            # 如果找不到TrueType字体，使用默认字体
            font = ImageFont.load_default()
            logger.info("无法加载任何TrueType字体，使用默认字体")

        # 画网格
        for i in range(self.board_size):
            # 横线
            draw.line([(margin + i * cell_size + cell_size // 2, margin + cell_size // 2),
                      (margin + i * cell_size + cell_size // 2, img_size - margin - cell_size // 2)], fill="black")
            # 竖线
            draw.line([(margin + cell_size // 2, margin + i * cell_size + cell_size // 2),
                      (img_size - margin - cell_size // 2, margin + i * cell_size + cell_size // 2)], fill="black")
            
            # 添加坐标数字
            text = str(i)
            # 获取文本大小以便居中显示
            try:
                text_bbox = font.getbbox(text)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            except:
                # 默认字体可能不支持getbbox，使用估算值
                text_width = len(text) * 6
                text_height = 8
            
            # 上边和下边的数字
            x = margin + i * cell_size + cell_size // 2 - text_width // 2
            draw.text((x, 2), text, fill="black", font=font)
            draw.text((x, img_size - margin + 2), text, fill="black", font=font)
            
            # 左边和右边的数字
            y = margin + i * cell_size + cell_size // 2 - text_height // 2
            draw.text((2, y), text, fill="black", font=font)
            draw.text((img_size - margin + 2, y), text, fill="black", font=font)

        # 画棋子
        for y in range(self.board_size):
            for x in range(self.board_size):
                if board[y][x] != 0:
                    color = "black" if board[y][x] == 1 else "white"
                    draw.ellipse([(margin + x * cell_size + 5, margin + y * cell_size + 5),
                                (margin + x * cell_size + cell_size - 5, margin + y * cell_size + cell_size - 5)],
                                fill=color, outline="black")

        # 高亮最后一步落子
        if last_move:
            x, y = last_move
            draw.rectangle([(margin + x * cell_size, margin + y * cell_size),
                          (margin + x * cell_size + cell_size, margin + y * cell_size + cell_size)],
                          outline="red", width=3)

        path = "gomoku_board.png"
        img.save(path)
        return path

    def check_win(self, board, x, y):
        """检查是否胜利"""
        player = board[y][x]
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]

        for dx, dy in directions:
            count = 1
            for d in (1, -1):
                nx, ny = x, y
                while True:
                    nx += dx * d
                    ny += dy * d
                    if 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[ny][nx] == player:
                        count += 1
                    else:
                        break
            if count >= 5:
                return True
        return False

    def is_board_full(self, board):
        """检查棋盘是否已满"""
        return all(all(cell != 0 for cell in row) for row in board)

    def perform_undo(self, session_id):
        """执行悔棋操作，回退一步"""
        if not self.can_undo(session_id):
            return False
        
        # 移除当前状态
        self.board_history[session_id].pop()
        self.last_move_history[session_id].pop()
        
        # 获取前一个状态
        previous_board = self.board_history[session_id][-1]
        previous_move = self.last_move_history[session_id][-1]
        
        # 更新当前游戏状态
        self.games[session_id] = copy.deepcopy(previous_board)
        
        return True, previous_move

    @filter.command("gomoku pvp")
    async def start_pvp(self, event: AstrMessageEvent):
        """群聊PVP模式，等待两名玩家加入游戏"""
        session_id = self.get_session_id(event)
        if session_id in self.pvp_sessions:
            yield event.plain_result("已经有一场 PVP 对局在进行！")
            return
        self.pvp_sessions[session_id] = {"players": []}  # 存储玩家ID列表
        self.current_player[session_id] = None
        yield event.plain_result("PVP 模式开启，请输入 /gomoku join 加入游戏！输入 /gomoku end 可以结束当前游戏。")

    @filter.command("gomoku")
    async def handle_gomoku(self, event: AstrMessageEvent, command: str = ""):
        """五子棋游戏指令"""
        session_id = self.get_session_id(event)
        player_id = self.get_player_id(event)

        if command == "pvp":
            return
        
        # 处理加入游戏命令
        if command == "join":
            if session_id not in self.pvp_sessions:
                yield event.plain_result("当前没有进行中的游戏，请先使用 /gomoku pvp 开始一局游戏！")
                return

            players = self.pvp_sessions[session_id]["players"]
            
            if player_id in players:
                yield event.plain_result("你已经在游戏中了！")
                return

            if len(players) >= 2:
                yield event.plain_result("游戏已满，无法加入！")
                return

            # 保存玩家名字
            sender_name = event.get_sender_name()
            if sender_name is None or sender_name == "" or sender_name == "unknown":  # 更明确的条件检查
                sender_name = f"玩家{len(players) + 1}"
            self.save_player_name(player_id, sender_name)
            
            players.append(player_id)
            player_name = self.get_player_name(player_id)
            
            if len(players) == 1:
                yield event.plain_result(f"{player_name} 加入对局！等待另一位玩家加入。")
            elif len(players) == 2:
                self.current_player[session_id] = players[0]
                first_player_name = self.get_player_name(players[0])
                
                # 初始化一个空棋盘并保存到历史记录中
                board = self.create_board()
                self.games[session_id] = board
                self.save_board_state(session_id, board)
                
                yield event.plain_result(f"{player_name} 加入对局！游戏开始，{first_player_name}（黑子）先落子 /gomoku (x,y)  /gomoku undo 悔棋 /gomoku surrender 投降 /gomoku end 结束游戏。")
            return

        # 处理结束游戏命令
        if command == "end":
            if session_id not in self.pvp_sessions:
                yield event.plain_result("当前没有进行中的游戏！")
                return
                
            players = self.pvp_sessions[session_id]["players"]
            
            if player_id not in players:
                yield event.plain_result("只有游戏参与者才能结束游戏！")
                return
            
            player_name = self.get_player_name(player_id)
            # 安全删除游戏数据
            if session_id in self.games:
                del self.games[session_id]
            if session_id in self.board_history:
                del self.board_history[session_id]
            if session_id in self.last_move_history:
                del self.last_move_history[session_id]
            if session_id in self.undo_requests:
                del self.undo_requests[session_id]
            del self.pvp_sessions[session_id]
            if session_id in self.current_player:
                del self.current_player[session_id]
            yield event.plain_result(f"游戏已被 {player_name} 结束！")
            return

        # 处理投降命令
        if command == "surrender":
            if session_id not in self.pvp_sessions:
                yield event.plain_result("当前没有进行中的游戏！")
                return
                
            players = self.pvp_sessions[session_id]["players"]
            
            if player_id not in players:
                yield event.plain_result("你不是游戏玩家！")
                return
                
            winner_id = players[1] if player_id == players[0] else players[0]
            player_name = self.get_player_name(player_id)
            winner_name = self.get_player_name(winner_id)
            
            yield event.plain_result(f"🏳️ {player_name} 投降了！{winner_name} 获胜！")
            
            # 安全删除游戏数据
            if session_id in self.games:
                del self.games[session_id]
            if session_id in self.board_history:
                del self.board_history[session_id]
            if session_id in self.last_move_history:
                del self.last_move_history[session_id]
            if session_id in self.undo_requests:
                del self.undo_requests[session_id]
            del self.pvp_sessions[session_id]
            if session_id in self.current_player:
                del self.current_player[session_id]
            return
            
        # 处理悔棋请求命令
        if command == "undo":
            if session_id not in self.pvp_sessions:
                yield event.plain_result("当前没有进行中的游戏！")
                return
                
            players = self.pvp_sessions[session_id]["players"]
            
            if player_id not in players:
                yield event.plain_result("你不是游戏玩家！")
                return
                
            if player_id == self.current_player[session_id]:
                yield event.plain_result("当前是你的回合，不能悔棋！")
                return
                
            if not self.can_undo(session_id):
                yield event.plain_result("当前无法悔棋！")
                return
                
            # 记录悔棋请求
            self.undo_requests[session_id] = player_id
            
            # 获取对方玩家ID和名字
            opponent_id = players[0] if player_id == players[1] else players[1]
            player_name = self.get_player_name(player_id)
            opponent_name = self.get_player_name(opponent_id)
            
            yield event.plain_result(f"{player_name} 请求悔棋，{opponent_name} 请输入 /gomoku accept 同意，或 /gomoku reject 拒绝。")
            return
            
        # 处理接受悔棋命令
        if command == "accept":
            if session_id not in self.pvp_sessions or session_id not in self.undo_requests:
                yield event.plain_result("当前没有待处理的悔棋请求！")
                return
                
            players = self.pvp_sessions[session_id]["players"]
            requester_id = self.undo_requests[session_id]
            
            if player_id not in players:
                yield event.plain_result("你不是游戏玩家！")
                return
                
            if player_id == requester_id:
                yield event.plain_result("你不能批准自己的悔棋请求！")
                return
                
            # 执行悔棋
            success, previous_move = self.perform_undo(session_id)
            if not success:
                yield event.plain_result("悔棋失败，无法回退到上一步！")
                return
                
            # 交换当前玩家
            self.current_player[session_id] = requester_id
            
            # 获取玩家名字
            requester_name = self.get_player_name(requester_id)
            accepter_name = self.get_player_name(player_id)
            
            # 清除悔棋请求
            del self.undo_requests[session_id]
            
            # 显示悔棋后的棋盘
            board = self.games[session_id]
            yield event.image_result(self.draw_board(board, previous_move, session_id))
            yield event.plain_result(f"{accepter_name} 同意了 {requester_name} 的悔棋请求！轮到 {requester_name} 落子。")
            return
            
        # 处理拒绝悔棋命令
        if command == "reject":
            if session_id not in self.pvp_sessions or session_id not in self.undo_requests:
                yield event.plain_result("当前没有待处理的悔棋请求！")
                return
                
            players = self.pvp_sessions[session_id]["players"]
            requester_id = self.undo_requests[session_id]
            
            if player_id not in players:
                yield event.plain_result("你不是游戏玩家！")
                return
                
            if player_id == requester_id:
                yield event.plain_result("你不能拒绝自己的悔棋请求！")
                return
                
            # 获取玩家名字
            requester_name = self.get_player_name(requester_id)
            rejecter_name = self.get_player_name(player_id)
            
            # 清除悔棋请求
            del self.undo_requests[session_id]
            
            yield event.plain_result(f"{rejecter_name} 拒绝了 {requester_name} 的悔棋请求！游戏继续。")
            return

        # 处理落子
        if session_id not in self.pvp_sessions:
            yield event.plain_result("当前没有进行中的游戏，请先使用 /gomoku_pvp 开始一局游戏！")
            return
            
        players = self.pvp_sessions[session_id]["players"]
        if len(players) < 2:
            yield event.plain_result("游戏还未开始，等待玩家加入...")
            return
        if player_id not in players:
            yield event.plain_result("你不是游戏玩家！请等待当前游戏结束后加入。")
            return
        if player_id != self.current_player[session_id]:
            current_player_name = self.get_player_name(self.current_player[session_id])
            yield event.plain_result(f"当前是 {current_player_name} 的回合！")
            return

        if not command:
            yield event.plain_result("请发送坐标，格式：(x,y)，或输入 /gomoku surrender 投降。")
            return
        
        match = re.match(r"\((\d+),(\d+)\)", command)
        if not match:
            yield event.plain_result("请发送 (x,y) 格式的坐标！例如：(7,7) 表示下在第7行第7列。")
            return
        
        x, y = map(int, match.groups())
        if not (0 <= x < self.board_size and 0 <= y < self.board_size):
            yield event.plain_result(f"坐标 ({x},{y}) 超出棋盘范围！横坐标和纵坐标都应该在 0-{self.board_size-1} 之间。")
            return

        board = self.games.setdefault(session_id, self.create_board())
        
        if board[y][x] != 0:
            yield event.plain_result("此处已有棋子！")
            return
        
        # 确定玩家颜色和索引
        player_index = 0 if player_id == players[0] else 1
        player_color = 1 if player_index == 0 else 2
        
        # 玩家落子
        board[y][x] = player_color
        # 保存当前棋盘状态到历史记录
        self.save_board_state(session_id, board, (x, y))
        
        if self.check_win(board, x, y):
            # 安全删除游戏数据
            if session_id in self.games:
                del self.games[session_id]
            if session_id in self.board_history:
                del self.board_history[session_id]
            if session_id in self.last_move_history:
                del self.last_move_history[session_id]
            if session_id in self.undo_requests:
                del self.undo_requests[session_id]
            if session_id in self.pvp_sessions:
                winner_name = self.get_player_name(player_id)
                del self.pvp_sessions[session_id]
                if session_id in self.current_player:
                    del self.current_player[session_id]
                yield event.image_result(self.draw_board(board, (x, y), session_id))
                yield event.plain_result(f"🎉 {winner_name} 赢了！游戏结束。")
            return
        
        # 检查是否和局
        if self.is_board_full(board):
            # 安全删除游戏数据
            if session_id in self.games:
                del self.games[session_id]
            if session_id in self.board_history:
                del self.board_history[session_id]
            if session_id in self.last_move_history:
                del self.last_move_history[session_id]
            if session_id in self.undo_requests:
                del self.undo_requests[session_id]
            if session_id in self.pvp_sessions:
                del self.pvp_sessions[session_id]
                if session_id in self.current_player:
                    del self.current_player[session_id]
            yield event.image_result(self.draw_board(board, (x, y), session_id))
            yield event.plain_result("⭕️ 棋盘已满，游戏结束，双方和局！")
            return
        
        # 切换当前玩家
        next_player_index = 1 - player_index
        next_player_id = players[next_player_index]
        self.current_player[session_id] = next_player_id
        next_player_name = self.get_player_name(next_player_id)
        yield event.image_result(self.draw_board(board, (x, y), session_id))
        yield event.plain_result(f"轮到 {next_player_name}（{'黑子' if next_player_index == 0 else '白子'}）下棋！")

