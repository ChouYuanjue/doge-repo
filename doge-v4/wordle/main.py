import os
import random
import json
from io import BytesIO

from PIL import Image as ImageW   
from PIL import ImageDraw, ImageFont

from astrbot.api.all import *
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star, register
import re

try:
    os.system("python -m pip install pyspellchecker")  
except:
    logger.info("Pyspellchecker not installed this time.")

from spellchecker import SpellChecker

def re_spell_check(word: str, re_word_list: list):  
    for each_word in re_word_list:
        if re.search(f'{each_word}',word):
            return True
        
class WordleGame:
    def __init__(self, answer: str):
        self.answer = answer.upper()
        self.length = len(answer)
        self.max_attempts = self.length + 1
        self.guesses: list[str] = []
        self.feedbacks: list[list[int]] = []
        self.history_letters: list[str] = []
        self.history_words: list[str] = []

        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))  
        self.font_file = os.path.join(self.plugin_dir, "MinecraftAE.ttf")   

        self._font = ImageFont.truetype(self.font_file, 40) 

    async def gen_image(self) -> bytes:
        CELL_COLORS = {
            2: (106, 170, 100),
            1: (201, 180, 88),
            0: (120, 124, 126),
            -1: (211, 214, 218),
        }
        BACKGROUND_COLOR = (255, 255, 255)
        TEXT_COLOR = (255, 255, 255)

        CELL_SIZE = 60
        CELL_MARGIN = 5
        GRID_MARGIN = 5

        cell_stride = CELL_SIZE + CELL_MARGIN
        width = GRID_MARGIN * 2 + cell_stride * self.length - CELL_MARGIN
        height = GRID_MARGIN * 2 + cell_stride * self.max_attempts - CELL_MARGIN

        image = ImageW.new("RGB", (width, height), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(image)

        for row in range(self.max_attempts):
            y = GRID_MARGIN + row * cell_stride

            for col in range(self.length):
                x = GRID_MARGIN + col * cell_stride

                if row < len(self.guesses) and col < len(self.guesses[row]):
                    letter = self.guesses[row][col].upper()
                    feedback_value = self.feedbacks[row][col]
                    cell_color = CELL_COLORS[feedback_value]
                else:
                    letter = ""
                    cell_color = CELL_COLORS[-1]

                draw.rectangle(
                    [x, y, x + CELL_SIZE, y + CELL_SIZE], fill=cell_color, outline=None
                )

                if letter:
                    text_bbox = draw.textbbox((0, 0), letter, font=self._font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]

                    letter_x = x + (CELL_SIZE - text_width) // 2 + 2.5
                    letter_y = y + (CELL_SIZE - text_height) // 2 + 1

                    draw.text((letter_x, letter_y), letter, fill=TEXT_COLOR, font=self._font)

        with BytesIO() as output:
            image.save(output, format="PNG")
            return output.getvalue()

    async def gen_image_hint(self,word) -> bytes:   
        CELL_COLORS = {
            2: (106, 170, 100),
            1: (201, 180, 88),
            0: (120, 124, 126),
            -1: (211, 214, 218),
        }
        BACKGROUND_COLOR = (255, 255, 255)
        TEXT_COLOR = (255, 255, 255)

        CELL_SIZE = 60
        CELL_MARGIN = 5
        GRID_MARGIN = 5

        cell_stride = CELL_SIZE + CELL_MARGIN
        width = GRID_MARGIN * 2 + cell_stride * self.length - CELL_MARGIN
        height = GRID_MARGIN * 2 + cell_stride * 1 - CELL_MARGIN

        image = ImageW.new("RGB", (width, height), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(image)

        for row in range(1):
            y = GRID_MARGIN + row * cell_stride

            for col in range(self.length):
                x = GRID_MARGIN + col * cell_stride

                if word[col] == " ":
                    cell_color = CELL_COLORS[-1]
                else:
                    cell_color = CELL_COLORS[2]
                letter = word[col]

                draw.rectangle(
                    [x, y, x + CELL_SIZE, y + CELL_SIZE], fill=cell_color, outline=None
                )

                text_bbox = draw.textbbox((0, 0), letter, font=self._font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

                letter_x = x + (CELL_SIZE - text_width) // 2 + 2.5
                letter_y = y + (CELL_SIZE - text_height) // 2 + 1

                draw.text((letter_x, letter_y), letter, fill=TEXT_COLOR, font=self._font)

        with BytesIO() as output:
            image.save(output, format="PNG")
            return output.getvalue()

    async def is_guessed(self, word: str) -> bool:
        word = word.upper()
        if word in self.history_words:
            logger.info(f"{word}这个单词已经猜过了。")
            return True
        else:
            self.history_words.append(word)
            logger.info(f"is_guessed():历史猜测的单词表更新为{self.history_words}")
            return False

    async def guess(self, word: str) -> bytes:
        word = word.upper()
        self.guesses.append(word)

        for i in range(len(word)):
            # 比如，历史字母表为["a","r","r","r"]（有3个r），此时用户输入refer（有2个r），历史字母表就不会再添加r了
            # 而如果，历史字母表为["a","r"]（有1个r），此时用户输入refer（有2个r），历史字母表也会变成2个r
            if word.count(word[i]) > self.history_letters.count(word[i]):
                self.history_letters.append(word[i])

        logger.info(f"guess():历史猜测的字母表更新为{self.history_letters}。")

        feedback = [0] * self.length
        answer_char_counts: dict[str, int] = {}
        
        for i in range(self.length):
            if word[i] == self.answer[i]:
                feedback[i] = 2
            else:
                answer_char_counts[self.answer[i]] = answer_char_counts.get(self.answer[i], 0) + 1
        
        for i in range(self.length):
            if feedback[i] != 2:
                char = word[i]
                if char in answer_char_counts and answer_char_counts[char] > 0:
                    feedback[i] = 1
                    answer_char_counts[char] -= 1
        
        self.feedbacks.append(feedback)
        result = await self.gen_image()

        return result
    
    async def hint(self) -> bytes:   # 原理和guess()相同，但本函数无需传参
        tem = 0
        for i in range(len(self.answer)):
            if self.answer[i] in self.history_letters:
                tem += 1
        if not tem >= 1:
            logger.info("用户还未猜出任何字母。")
            return False

        else:
            # 组建“提示”的单词，未猜出的字母用空格代替
            hint_word = ""
            tem1 = self.history_letters.copy()  # 这里使用copy()是因为：在 Python 中，当你执行 tem1 = self.history_letters 时，tem1 并没有创建一个新的独立对象，而是指向了与 self.history_letters 相同的对象（即它们共享同一块内存地址）。此时，如果 self.history_letters 是可变对象（如列表、字典、集合等），修改 tem1 的内容会导致 self.history_letters 同步变化，因为二者本质上是同一个对象的不同引用。
            for i in range(len(self.answer)):
                if self.answer[i] in tem1:
                    hint_word = hint_word + self.answer[i]
                    tem1.remove(self.answer[i])  # 举个例子，这是为了避免出现这样一种情况：历史字母表只有一个“r”字母，但提示的单词却给出了更多“r”
                else:
                    hint_word = hint_word + " "
            hint_word = hint_word.upper()
            
            # 将组建的“提示”单词生成图片
            result = await self.gen_image_hint(hint_word)

            return result
    
    @property
    def is_game_over(self):
        if not self.guesses:
            return False
        return len(self.guesses) >= self.max_attempts

    @property
    def is_won(self):
        return self.guesses and self.guesses[-1].upper() == self.answer


@register(
    "doge_wordle",
    "Raven95676, whzc",
    "Wordle游戏（响应指令内容版），支持指定位数",
    "2.2.1",
    "https://github.com/whzcc/astrbot_plugin_wordle_2_cmd",
)

class PluginWordle(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.game_sessions: dict[str, WordleGame] = {}
        # 加载配置文件
        self.config = config
        
        # 自定义拼写检查
        self.custom_word_list = self.config.get("custom_word_list", "").split(";")

    @staticmethod
    async def get_answer(length):
        try:
            wordlist_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "wordlist"
            )

            if not os.path.exists(wordlist_path):
                logger.error("词表文件不存在")
                return None

            # 获取单词文件
            word_file_list = os.listdir(wordlist_path)
            global word_dict
            word_dict = {}
            # 遍历单词表，并用字典接收内容
            for word_file in word_file_list:
                with open(os.path.join(wordlist_path,word_file),"r",encoding="utf-8") as f:
                    word_dict.update(json.load(f)) 
                    # 只保留长度为length的单词
                    for word in list(word_dict.keys()):
                        if len(word) != length:
                            del word_dict[word]

            # 随机选一个单词
            word = random.choice(list(word_dict.keys()))
            global explanation
            explanation = word_dict[word]["中释"]

            logger.info(f"选择了{word}单词，长度{length}，释义为{explanation}")

            return word.upper()
        
        except Exception as e:
            logger.error(f"加载词表失败: {e!s}")
            return None
        
    @command_group("wordle")  
    def wordle(self):
        pass

    @wordle.command("end")  
    async def stop_wordle(self, event: AstrMessageEvent):
        """结束游戏"""
        session_id = event.unified_msg_origin
        if session_id not in self.game_sessions:
            yield event.plain_result("游戏还没开始，输入“/猜单词 开始”来开始游戏吧！")
            return
        if session_id in self.game_sessions:
            game = self.game_sessions[session_id]
            yield event.plain_result(f"猜单词已结束，正确答案是{game.answer}。")
            del self.game_sessions[session_id]

    @wordle.command("hint")  # type: ignore
    async def give_hint(self, event: AstrMessageEvent):
        """获取提示"""
        session_id = event.unified_msg_origin
        if session_id not in self.game_sessions:
            yield event.plain_result("游戏还没开始，输入“/猜单词 开始”来开始游戏吧！")
            return
        game = self.game_sessions[session_id]

        image_result_hint = await game.hint()

        if not image_result_hint == False:  # 当用户猜出来过正确的字母时，给出图片形式的提示
            
            # 保证兼容性（从原作者那偷的），将png转为jpg
            tem_id = session_id.replace(":","") # 删掉文件系统不兼容的符号
            img_path_png = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"{tem_id}_{len(game.guesses)}_wordle_hint.png",
            )
            img_path_jpg = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"{tem_id}_{len(game.guesses)}_wordle_hint.jpg",
            )

            with open(img_path_png, "wb") as f:
                f.write(image_result_hint)

            im = ImageW.open(img_path_png)
            im = im.convert('RGB')
            im.save(img_path_jpg, quality=95)

            chain = [
                Image.fromFileSystem(img_path_jpg),
                Plain("这是你已经猜出的字母。")
            ]
            yield event.chain_result(chain)

            os.remove(img_path_png)
            os.remove(img_path_jpg)

        else:   # 当用户一个字母都没有猜出来过时，给出文本形式的提示
            i = random.randint(0,len(game.answer)-1)
            hint = f"提示：第{i+1}个字母是 {game.answer[i]}。"
            yield event.plain_result(hint)
    
    @wordle.command("start")  # type: ignore
    async def start_wordle(self, event: AstrMessageEvent, length = 5):
        """开始Wordle游戏"""
        answer = await self.get_answer(length)
        session_id = event.unified_msg_origin
        if session_id in self.game_sessions:
            del self.game_sessions[session_id]
        if not answer:
            random_text = random.choice([
                f"{length}个字母长度的单词，我找不到啊……",
                f"{length}个字母的单词好像有点稀有哦，换一个吧！",
                "没找到这么长的单词，换一个吧！"
            ])
            yield event.plain_result(random_text)
        else:
            game = WordleGame(answer)
            self.game_sessions[session_id] = game
            logger.debug(f"答案是：{answer}")
            random_text = random.choice([
                    f"游戏开始！请输入长度为{length}的单词。",
                    f"游戏开始了！请输入长度为{length}的单词。",
                    f"游戏开始了！请输入长度为{length}的单词。"
                ])
            yield event.plain_result(random_text)
        pass

    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):

        msg = event.get_message_str()
        msg = msg.lower()
        session_id = event.unified_msg_origin

        if session_id in self.game_sessions and event.is_at_or_wake_command:
            game = self.game_sessions[session_id]

            if "猜单词 开始" in msg or "猜单词 结束" in msg or "猜单词 提示" in msg:
                return
            
            else:
                
                length = game.length
                spellcheck = SpellChecker()

                if not msg.isalpha():
                    random_text = random.choice([
                    "你要输入英语才行啊😉！",
                    "语言不正确哦，要输入英语单词。",
                    "我以后就可以用其他语言猜单词了，不过现在还是用英语吧！",
                    "Try in English💬!", 
                    "需要英文单词～🔡",  
                    "Alphabet Only!🔤", 
                    "外星挑战：地球英文输入🛸。", 
                    "符号错误🔣，需要纯字母。", 
                    "❗Error: Expected ENGLISH :("
                ])
                    random_text = random_text + "\n输入“/猜单词 结束”就可以结束游戏，输入“/猜单词 提示”可以获得提示。"
                    yield event.plain_result(random_text)
                    return
                
                elif len(msg) != length:
                    random_text = random.choice([
                    f"你要输入{length}字母的英语单词才行啊😉！",
                    f"不太对哦，要输入{length}个字母的英语单词🔡。",
                    f"Traceback (most recent call last):\n  File \"\<wordle\>\", line 114, in \<module\>\nSpellError: I need {length}-letter English words! :(",
                    f"需要{length}个字母长的英语单词～🔡", 
                    f"输入有问题！请输入{length}个字母长的英语单词。",
                    f"回答错误❌！应该是有{length}个字母的英语单词。",
                    f"戳啦🌀！请输入{length}个字母的英语单词。"

                ])
                    random_text = random_text + "\n输入“/猜单词 结束”就可以结束游戏，输入“/猜单词 提示”可以获得提示。"
                    yield event.plain_result(random_text)
                    return   
                    
                elif not(
                    msg in list(word_dict.keys())   # 在词表中是否找到用户的输入
                    or spellcheck.known((msg,)) # 在拼写检查库中是否找到用户的输入
                    or (re_spell_check(msg,self.custom_word_list))
                    ):
                    random_text = random.choice([
                    "拼写错误😉！",
                    "拼错了哦，试试重新拼一下单词吧！",
                    "单词拼写不正确！",
                    "拼写有误🌀，再试一次吧！",
                    "（你确定这个单词存在吗😲？）",
                    "拼写错误，请检查拼写！",
                    ])
                    random_text = random_text + "\n输入“/猜单词 结束”就可以结束游戏，输入“/猜单词 提示”可以获得提示。"
                    yield event.plain_result(random_text)
                    return
            
            if not await game.is_guessed(msg):
                image_result = await game.guess(msg)
            else:
                yield event.plain_result("这个单词已经猜过了！")
                return

            if game.is_won:
                sender_info = event.get_sender_name() if event.get_sender_name() else event.get_sender_id()
                random_text = random.choice([
                    "恭喜你猜对了😉！",
                    "Cool🎉！",
                    "答案正确✅！"
                    "太棒了🎉！", 
                    "猜中啦🎯！",  
                    "冠军🥇！", 
                    "天才🌟！", 
                    "胜利🏆！", 
                    "满分💯！", 
                    "王者👑！", 
                    "绝了🤩！"
                ])
                if random.randint(1,22) == 1:
                    random_text = "🔠🥳语言神，启动🔠🥳！"
                game_status = f"{random_text}“{game.answer}”的意思是“{explanation}”。"
                del self.game_sessions[session_id]
            elif game.is_game_over:
                game_status = f"没有人猜出答案啊Σ(°△°|||)︴\n正确答案是“{game.answer}”，意思是“{explanation}”。"
                del self.game_sessions[session_id]
            else:
                game_status = f"已猜测 {len(game.guesses)}/{game.max_attempts} 次。"
                logger.info(f"已猜测 {len(game.guesses)}/{game.max_attempts} 次。")
            
            # 保证兼容性（从原作者那偷的），将png转为jpg
            tem_id = session_id.replace(":","") # 删掉文件系统不兼容的符号
            img_path_png = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"{tem_id}_{len(game.guesses)}_wordle.png",
            )
            img_path_jpg = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"{tem_id}_{len(game.guesses)}_wordle.jpg",
            )

            with open(img_path_png, "wb") as f:
                f.write(image_result)

            im = ImageW.open(img_path_png)
            im = im.convert('RGB')
            im.save(img_path_jpg, quality=95)
            chain = [
                Image.fromFileSystem(img_path_jpg),
                Plain(game_status),
            ]

            yield event.chain_result(chain)

            os.remove(img_path_png)
            os.remove(img_path_jpg)
