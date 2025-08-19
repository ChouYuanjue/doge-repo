import os
import random
import re
import shutil
from difflib import SequenceMatcher
from typing import Tuple, Optional
from pathlib import Path

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register


@register("doge_lyrics", "EEEpai", "发送一句歌词，机器人会回复下一句", "1.2.2")
class LyricNextPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 存储配置
        self.config = config
        # 初始化歌词索引
        self.default_lyrics_dir = os.path.join(os.path.dirname(__file__), "data", "lyrics")  # 插件内默认歌词目录
        
        astrbot_root = Path(__file__).resolve().parent.parent.parent
        self.lyrics_dir = os.path.join(astrbot_root, "lyrics_data")  # 用户持久化歌词目录
        
        self.lyrics_index = {}  # 歌词句子 -> [(下一句, 歌名), ...]
        self.lyrics_info = {}  # 歌名 -> 歌曲信息(作者等)

        # 确保用户歌词目录存在 - 这是主要的歌词加载目录
        os.makedirs(self.lyrics_dir, exist_ok=True)
        logger.info(f"用户歌词目录: {self.lyrics_dir}")
        
        # 确保默认歌词目录存在（仅用于转移）
        if not os.path.exists(self.default_lyrics_dir):
            os.makedirs(self.default_lyrics_dir, exist_ok=True)
            logger.info(f"创建默认歌词目录: {self.default_lyrics_dir}")

    async def _migrate_default_lyrics(self):
        """将插件内默认歌词文件夹的内容增量迁移到用户的持久化数据目录"""
        try:
            # 检查插件内默认歌词目录是否存在且有文件
            if not os.path.exists(self.default_lyrics_dir):
                logger.info("插件内默认歌词目录不存在，跳过迁移")
                return
                
            default_files = [f for f in os.listdir(self.default_lyrics_dir) if f.endswith('.txt')]
            if not default_files:
                logger.info("插件内默认歌词目录为空，跳过迁移")
                return
            
            # 获取用户目录中已有的文件
            existing_files = set()
            if os.path.exists(self.lyrics_dir):
                existing_files = set(f for f in os.listdir(self.lyrics_dir) if f.endswith('.txt'))
            
            # 计算需要迁移的文件（增量迁移，不覆盖已有文件）
            files_to_migrate = []
            for filename in default_files:
                if filename not in existing_files:
                    files_to_migrate.append(filename)
            
            if not files_to_migrate:
                logger.info("所有插件内默认歌词文件已存在于用户目录，无需迁移")
                return
            
            # 执行迁移
            migrated_count = 0
            for filename in files_to_migrate:
                try:
                    src_path = os.path.join(self.default_lyrics_dir, filename)
                    dst_path = os.path.join(self.lyrics_dir, filename)
                    
                    # 复制文件而不是移动，保留原始文件
                    shutil.copy2(src_path, dst_path)
                    migrated_count += 1
                    
                except Exception as e:
                    logger.error(f"迁移歌词文件 {filename} 失败: {str(e)}")
            
            if migrated_count > 0:
                logger.info(f"成功从插件内目录迁移 {migrated_count} 个默认歌词文件到用户持久化目录")
            
        except Exception as e:
            logger.error(f"迁移插件内默认歌词文件时发生错误: {str(e)}")

    def _contains_chinese(self, text: str) -> bool:
        """检测文本是否包含汉字"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    async def _migrate_lyrics_if_enabled(self):
        """根据配置决定是否迁移默认歌词到用户目录"""
        if self.config.get("auto_import_default_lyrics", True):
            logger.info("自动导入默认歌词库已启用，开始迁移歌词...")
            await self._migrate_default_lyrics()
        else:
            logger.info("自动导入默认歌词库已禁用，跳过迁移歌词")

    async def initialize(self):
        """插件初始化，加载所有歌词文件并建立索引"""
        logger.info("正在初始化 LyricNext 插件...")
        
        # 根据配置决定是否迁移默认歌词到用户目录
        await self._migrate_lyrics_if_enabled()
        
        # 然后加载歌词
        await self._load_lyrics()
        logger.info(
            f"LyricNext 插件初始化完成，已加载 {len(self.lyrics_info)} 首歌曲，{len(self.lyrics_index)} 条歌词索引")

    def _find_song_by_name(self, song_name: str) -> Tuple[int, str]:
        """根据歌曲名查找目录中的歌曲，返回 (匹配状态, 歌曲路径)
        匹配状态: 0 - 完全匹配, 1 - 模糊匹配, 2 - 未找到
        """
        # 查找匹配的歌曲
        song_name = song_name.strip()
        exact_matches = []
        fuzzy_matches = []

        # 首先尝试精确匹配
        for existing_song in self.lyrics_info.keys():
            if song_name.lower() == existing_song.lower():
                exact_matches.append(existing_song)

        # 如果有精确匹配，使用精确匹配结果
        if exact_matches:
            return 0, exact_matches[0]
        # 没有精确匹配，进行模糊匹配
        else:
            for existing_song in self.lyrics_info.keys():
                if song_name.lower() in existing_song.lower():
                    fuzzy_matches.append(existing_song)

            if not fuzzy_matches:
                return 2, ""

            if len(fuzzy_matches) > 1:
                # 多个模糊匹配结果，让用户选择
                song_list = "\n".join([f"  {song}" for song in fuzzy_matches])
                return 1, song_list

            # 唯一模糊匹配
            return 0, fuzzy_matches[0]

    async def _load_lyrics(self):
        """加载所有歌词文件并建立索引"""
        self.lyrics_index = {}
        self.lyrics_info = {}

        # 获取歌词目录下的所有文件
        try:
            for filename in os.listdir(self.lyrics_dir):
                if filename.endswith(".txt"):
                    song_name = os.path.splitext(filename)[0]
                    file_path = os.path.join(self.lyrics_dir, filename)

                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = [line.strip() for line in f.readlines() if line.strip()]

                            # 存储歌曲信息
                            self.lyrics_info[song_name] = {
                                "total_lines": len(lines)
                            }

                            # 建立歌词索引
                            # 首先将所有行拆分成句子（如果一行内有空格分隔的多句）
                            sentences = []
                            for line in lines:
                                # 先过滤掉明显的信息行和标题行
                                if (':' in line or '：' in line or  # 包含冒号的信息行
                                        ' - ' in line or  # 包含连字符的标题行（歌曲-歌手）
                                        '(' in line and ')' in line):  # 包含括号的标题行
                                    continue
                                # 检测行内是否有空格分隔的多句歌词
                                if ' ' in line.strip():
                                    # 只有包含汉字的歌词才进行空格拆分，英文歌不拆分
                                    if self._contains_chinese(line):
                                        # 将一行拆分成多句
                                        parts = [part.strip() for part in line.split(' ') if part.strip()]
                                        sentences.extend(parts)
                                    else:
                                        sentences.append(line.strip())
                                else:
                                    sentences.append(line.strip())
                            # 过滤掉空句子和无效句子
                            filtered_sentences = []
                            for sentence in sentences:
                                if (sentence and
                                        len(sentence) > 1 and  # 过滤单字符
                                        not sentence.isdigit() and  # 过滤纯数字
                                        not all(c in '()[]{}' for c in sentence)):  # 过滤纯括号
                                    filtered_sentences.append(sentence)

                            # 建立句子到下一句的索引
                            for i in range(len(filtered_sentences) - 1):
                                current_sentence = self._preprocess_lyrics(filtered_sentences[i]) if self.config[
                                    "preprocess_lyrics"] else filtered_sentences[i]
                                next_sentence = filtered_sentences[i + 1]

                                if current_sentence not in self.lyrics_index:
                                    self.lyrics_index[current_sentence] = []

                                self.lyrics_index[current_sentence].append((next_sentence, song_name))
                    except Exception as e:
                        logger.error(f"加载歌词文件 {filename} 失败: {str(e)}")
        except Exception as e:
            logger.error(f"遍历歌词目录失败: {str(e)}")

    def _preprocess_lyrics(self, lyrics: str) -> str:
        """预处理歌词，去除标点符号、emoji、QQ表情等，统一大小写等"""
        # 去除QQ表情格式 [表情:数字] 或类似格式
        processed = re.sub(r'\[表情:\d+\]', '', lyrics)
        processed = re.sub(r'\[[^\]]*\]', '', processed)  # 去除其他方括号格式
          # 去除emoji表情（更精确的Unicode范围）
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002700-\U000027BF"  # dingbats
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
            "\U00002600-\U000026FF"  # miscellaneous symbols
            "\U0001F780-\U0001F7FF"  # geometric shapes extended
            "]+", flags=re.UNICODE)
        processed = emoji_pattern.sub('', processed)

        # 去除标点符号，保留字母、数字、中文字符和空格
        # a-zA-Z0-9: 英文字母和数字
        # \u4e00-\u9fff: 中文字符
        # \s: 空格字符
        processed = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\s]', '', processed)

        # 去除多余空格
        processed = re.sub(r'\s+', ' ', processed).strip()
        # 转为小写
        processed = processed.lower()
        return processed

    async def _find_next_lyrics(self, lyrics: str) -> Optional[Tuple[str, str]]:
        """查找歌词的下一句，返回 (下一句, 歌曲名)"""
        # 直接查找精确匹配
        processed_lyrics = self._preprocess_lyrics(lyrics) if self.config["preprocess_lyrics"] else lyrics
        if processed_lyrics in self.lyrics_index:
            # 如果有多个匹配，随机选择一个
            return random.choice(self.lyrics_index[processed_lyrics])

        # 如果没有精确匹配，尝试模糊匹配
        match_threshold = self.config.get("match_threshold", 0.8)
        best_match = None
        best_similarity = 0.0

        for indexed_lyrics in self.lyrics_index.keys():
            # 计算相似度
            similarity = SequenceMatcher(None, processed_lyrics, indexed_lyrics).ratio()
            if similarity > best_similarity and similarity >= match_threshold:
                best_similarity = similarity
                best_match = indexed_lyrics

        # 如果找到了足够相似的匹配
        if best_match:
            logger.info(f"模糊匹配: '{processed_lyrics}' -> '{best_match}' (相似度: {best_similarity:.2f})")
            return random.choice(self.lyrics_index[best_match])

        # 没有找到匹配
        return None

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理所有消息，检查是否是歌词"""
        # 只处理纯文本消息
        message = event.message_str.strip()

        # 忽略命令前缀的消息
        if message.startswith('/'):
            return

        # 忽略空消息
        if not message:
            return

        # 检查消息链中是否只包含文本消息，过滤掉图片、戳一戳等非文本消息
        message_chain = event.get_messages()
        if not message_chain:
            return

        # 检查是否包含非文本消息组件
        for component in message_chain:
            component_type = type(component).__name__.lower()
            # 如果包含图片、戳一戳、语音、视频等非文本组件，则忽略
            if component_type in ['image', 'poke', 'record', 'video',  'at', 'reply']:
                return

        # 过滤掉看起来像HTML/XML的内容
        if '<' in message and '>' in message:
            return

        # 过滤掉过短或过长的消息
        if len(message) < 2 or len(message) > 50:
            return

        # 查找下一句歌词
        result = await self._find_next_lyrics(message)
        if result:
            next_lyrics, song_name = result
            yield event.plain_result(f"{next_lyrics}")
            # 阻止事件继续传播，避免被其他插件或LLM处理
            event.stop_event()

    @filter.command_group("lyrics")
    def lyrics_commands(self):
        """歌词相关命令组"""
        pass

    @lyrics_commands.command("help")
    async def help_command(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """歌词接龙插件使用帮助：
1. 直接发送歌词，机器人会回复下一句
2. /lyrics search 歌名 [歌手名] [音乐源] - 搜索并添加歌词到歌词库
   - 支持的音乐源: 网易云, QQ音乐, 酷狗
   - 歌手名和音乐源为可选参数
   - 示例: 
     * /lyrics search 晴天
     * /lyrics search 晴天 周杰伦
     * /lyrics search 晴天 周杰伦 QQ音乐
3. /lyrics list - 列出所有已添加的歌曲
4. /lyrics view 歌曲名 - 查看指定歌曲的完整歌词内容
5. /lyrics delete 歌曲名 - 从歌词库中删除指定歌曲
6. /lyrics reload - 重新加载所有歌词文件

💡 提示: 
- 如需批量下载某个歌手的所有歌曲，可运行 tools/fetch_lyrics.py
- 可单独运行 tools/search_lyrics.py 搜索单首歌曲"""
        yield event.plain_result(help_text)

    @lyrics_commands.command("reload")
    async def reload_command(self, event: AstrMessageEvent):
        """重新加载所有歌词"""
        # 根据配置决定是否迁移默认歌词到用户目录
        await self._migrate_lyrics_if_enabled()
            
        # 重新加载歌词
        await self._load_lyrics()
        yield (((
            (event.plain_result(
                f"已重新加载歌词库，共 {len(self.lyrics_info)} 首歌曲，{len(self.lyrics_index)} 条歌词索引")))))

    @lyrics_commands.command("search")
    async def search_command(self, event: AstrMessageEvent, song_name: str, artist_name: str = "",
                             music_source: str = ""):
        """搜索并添加歌词"""
        # 检查是否有歌曲名
        if not song_name:
            yield event.plain_result("请提供歌曲名称，格式：/lyrics search 歌名 [歌手名] [音乐源]")
            return  # 清理参数，将空字符串转为None
        artist_name = artist_name.strip() if artist_name.strip() else None
        music_source = music_source.strip() if music_source.strip() else None

        # 记录解析后的参数
        logger.info(f"解析后的参数: 歌名='{song_name}', 歌手='{artist_name}', 音乐源='{music_source}'")

        # 验证音乐源是否有效
        if music_source:
            valid_sources = ["网易云", "netease", "qq", "QQ音乐", "酷狗", "kugou"]
            if music_source.lower() not in [s.lower() for s in valid_sources]:
                yield event.plain_result(f"不支持的音乐源: {music_source}\n支持的音乐源: {', '.join(valid_sources)}")
                return

        # 根据输入的音乐源名称规范化为代码中使用的标识符
        source_mapping = {
            "网易云": "netease",
            "netease": "netease",
            "qq": "qq",
            "qq音乐": "qq",
            "酷狗": "kugou",
            "kugou": "kugou"
        }

        if music_source:
            music_source = source_mapping.get(music_source.lower(), music_source)
            yield event.plain_result(f"正在从{music_source}搜索《{song_name}》的歌词，请稍候...")
        else:
            yield event.plain_result(f"正在搜索《{song_name}》的歌词，请稍候...")
        try:
            # 导入搜索模块
            import sys
            import os
            tool_path = os.path.join(os.path.dirname(__file__), "tools")
            if tool_path not in sys.path:
                sys.path.append(tool_path)

            from search_lyrics import search_and_save_lyrics

            # 执行搜索，传入用户歌词目录
            logger.info(f"开始搜索歌词, 歌名:{song_name}, 歌手:{artist_name}, 音乐源:{music_source}")
            success, file_path, preview = search_and_save_lyrics(song_name, artist_name, music_source, self.lyrics_dir)
            logger.info(f"搜索结果: 成功={success}, 文件路径={file_path}")
            if success:
                # 重新加载歌词库以包含新添加的歌词
                await self._load_lyrics()

                # 提取文件名作为歌曲名
                song_name = os.path.basename(file_path).replace(".txt", "")

                # 发送成功消息和预览
                result = f"歌词《{song_name}》添加成功！\n\n歌词预览:\n{preview}"
                yield event.plain_result(result)
            else:
                if preview:  # 有歌词但保存失败
                    yield event.plain_result(f"获取到歌词但保存失败，请稍后再试。")
                else:
                    yield event.plain_result(f"未找到《{song_name}》的歌词，请尝试其他关键词或添加歌手名。")
        except Exception as e:
            logger.error(f"搜索歌词过程中发生错误: {str(e)}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"错误详情: {error_trace}")
            yield event.plain_result(f"搜索歌词失败: {str(e)}\n请检查日志获取详细信息。")

    @lyrics_commands.command("list")
    async def list_command(self, event: AstrMessageEvent):
        """列出所有已添加的歌曲"""
        if not self.lyrics_info:
            yield event.plain_result("歌词库为空，请先添加歌词")
            return

        song_list = "\n".join([f"{i + 1}. {song}" for i, song in enumerate(self.lyrics_info.keys())])
        yield (event.plain_result(f"已添加的歌曲列表（共{len(self.lyrics_info)}首）：\n{song_list}"))

    @lyrics_commands.command("view")
    async def view_command(self, event: AstrMessageEvent, song_name: str = ""):
        """查看指定歌曲的完整歌词内容"""
        if not song_name.strip():
            yield event.plain_result("请提供歌曲名称，格式：/lyrics view 歌曲名")
            return

        match_status, target_song = self._find_song_by_name(song_name)
        if match_status == 0:
            # 完全匹配
            file_path = os.path.join(self.lyrics_dir, f"{target_song}.txt")
        elif match_status == 1:
            # 模糊匹配
            yield event.plain_result(f"找到多首匹配的歌曲：\n\n{target_song}\n\n请使用更精确的歌曲名")
            return
        else:
            # 未找到
            yield event.plain_result(f"未找到包含 '{song_name}' 的歌曲\n使用 /lyrics list 查看所有歌曲")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lyrics_content = f.read().strip()

            if lyrics_content:
                # 限制显示长度，避免消息过长
                if len(lyrics_content) > 2000:
                    lyrics_preview = lyrics_content[:2000] + "\n...\n（歌词内容过长，已截断显示）"
                else:
                    lyrics_preview = lyrics_content

                yield event.plain_result(f"🎵 歌曲《{target_song}》的歌词内容：\n\n{lyrics_preview}")
            else:
                yield event.plain_result(f"歌曲《{target_song}》的歌词文件为空")
        except Exception as e:
            logger.error(f"读取歌词文件失败: {str(e)}")
            yield event.plain_result(f"读取歌曲《{target_song}》的歌词失败，请稍后再试")

    @lyrics_commands.command("delete")
    async def delete_command(self, event: AstrMessageEvent, song_name: str = ""):
        """删除指定歌曲的歌词文件"""
        if not song_name.strip():
            yield event.plain_result("请提供歌曲名称，格式：/lyrics delete 歌曲名")
            return

        match_status, target_song = self._find_song_by_name(song_name)
        if match_status == 0:
            # 完全匹配
            file_path = os.path.join(self.lyrics_dir, f"{target_song}.txt")
        elif match_status == 1:
            # 模糊匹配
            yield event.plain_result(f"找到多首匹配的歌曲：\n\n{target_song}\n\n请使用更精确的歌曲名")
            return
        else:
            # 未找到
            yield event.plain_result(f"未找到包含 '{song_name}' 的歌曲")
            return

        try:
            os.remove(file_path)
            # 重新加载歌词库以更新索引
            await self._load_lyrics()
            yield event.plain_result(f"已删除歌曲《{song_name}》的歌词")
        except Exception as e:
            logger.error(f"删除歌词文件失败: {str(e)}")
            yield event.plain_result(f"删除歌曲《{song_name}》的歌词失败")

    async def terminate(self):
        """插件终止时的清理工作"""
        logger.info("LyricNext 插件已终止")
