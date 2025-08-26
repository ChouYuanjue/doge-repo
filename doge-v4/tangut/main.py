import os
import json
import pickle
from PIL import Image, ImageDraw, ImageFont
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from collections import defaultdict
import jieba
import re

# 本插件调用的西夏文词典和字典数据来自于古今文字集成(ccamc.co)，由Github用户tinbreaker爬取，在此对二者表示感谢

class OptimizedDictEntry:
    """使用__slots__优化内存的字典条目类，兼容两种格式"""
    __slots__ = ('key', 'GX', 'GHC', 'LFW', 'explanationEN', 'explanationCN', 'entry_type')
    
    def __init__(self, data):
        # 确定条目类型和主键
        if "word" in data:
            self.key = data["word"]
            self.entry_type = "word"
        elif "character" in data:
            self.key = data["character"]
            self.entry_type = "character"
        else:
            self.key = ""
            self.entry_type = "unknown"
        
        self.GX = data.get("GX", "")
        self.GHC = data.get("GHC", "")
        self.LFW = data.get("LFW", "")
        self.explanationEN = data.get("explanationEN", "")
        self.explanationCN = data.get("explanationCN", "")
    
    def to_dict(self):
        """将条目转换为字典格式（用于序列化）"""
        result = {attr: getattr(self, attr) for attr in self.__slots__ if hasattr(self, attr)}
        # 根据条目类型设置正确的键名
        if self.entry_type == "word":
            result["word"] = result.pop("key")
        elif self.entry_type == "character":
            result["character"] = result.pop("key")
        return result
    
    def get_display_key(self):
        """获取用于显示的键名"""
        return f"{self.entry_type}: {self.key}"

class BilingualDictionary:
    """双向查询词典类，直接从JSON加载"""
    
    def __init__(self, dict_file_path):
        """直接加载JSON格式的词典"""
        print("正在加载词典...")
        
        # 初始化索引结构
        self.forward_index = {}
        self.reverse_index = defaultdict(list)
        
        # 加载JSON文件并构建索引
        with open(dict_file_path, 'r', encoding='utf-8') as f:
            dict_data = json.load(f)
            self._build_indexes(dict_data)
        
        print("词典加载完成!")
        
        # 初始化字符组合规则
        self.combine_rules = self._initialize_combine_rules()
    
    def _build_indexes(self, dict_data):
        """从JSON数据构建正向和反向索引"""
        for item in dict_data:
            entry = OptimizedDictEntry(item)
            
            # 添加到正向索引（西夏文 -> 条目）
            self.forward_index[entry.key] = entry
            
            # 添加到反向索引（关键词 -> 西夏文）
            # 从中文解释中提取关键词
            if entry.explanationCN:
                # 简单分词
                cn_keywords = [kw.strip() for kw in re.findall(r'[^，。！？；：]+', entry.explanationCN) if kw.strip()]
                for kw in cn_keywords:
                    # 排除数字和特殊标记
                    if not re.match(r'^[0-9【】]+$', kw):
                        self.reverse_index[kw].append(entry.key)
            
            # 从英文解释中提取关键词
            if entry.explanationEN:
                en_keywords = [kw.strip().lower() for kw in re.split(r'[\s.,;]+', entry.explanationEN) if kw.strip()]
                for kw in en_keywords:
                    self.reverse_index[kw].append(entry.key)
    
    def _initialize_combine_rules(self):
        """初始化字符组合规则系统"""
        # 基础组合模板
        combine_templates = {
            'PREV_EQUAL': {'combineWithPrevious': True, 'connector': '='},
            'PREV_HYPHEN': {'combineWithPrevious': True, 'connector': '-'},
            'NEXT_HYPHEN': {'combineWithNext': True, 'connector': '-'}
        }
        
        # 需要特殊处理组合的字符
        specific_rules = {
            '𗧓': {
                'variants': [
                    {'type': 'standalone', 'condition': lambda prev, next: not self._is_valid_char(prev), 
                     'GX': 'S1', 'GHC': 'Pronoun'}, 
                    {'type': 'combineWithPrevious', 'connector': '-', 
                     'condition': lambda prev, next: self._is_valid_char(prev), 
                     'GX': 'S2', 'GHC': 'Affix'}
                ]
            },
            
        }
        
        prev_equal_chars = ['𗫂', '𗅁', '𘆄', '𗇋', '𗗙', '𗦇']
        for char in prev_equal_chars:
            specific_rules[char] = combine_templates['PREV_EQUAL']
        
        prev_hyphen_chars = ['𘉞', '𗐱', '𗗟', '𗫶']
        for char in prev_hyphen_chars:
            specific_rules[char] = combine_templates['PREV_HYPHEN']
        
        return specific_rules
    
    def _is_valid_char(self, char):
        """检查字符是否为有效西夏文字符（非符号）"""
        return char and not re.match(r'[\p{P}\s]', char, re.UNICODE)
    
    def search_by_key(self, key):
        """通过西夏文字符或词查询相关条目，支持字符组合和变体规则"""
        # 1. 尝试直接匹配
        if key in self.forward_index:
            return self._apply_variant_rules(key, None, None)
        
        # 2. 尝试拆分组合字符进行匹配
        combined_results = self._process_character_combinations(key)
        if combined_results:
            return combined_results
        
        # 3. 尝试模糊匹配
        return self.fuzzy_search_key(key)
        
    def _process_character_combinations(self, input_str):
        chars = list(input_str)
        results = []
        i = 0
        
        while i < len(chars):
            current_char = chars[i]
            
            # 检查当前字符是否有组合规则
            if current_char in self.combine_rules:
                rule = self.combine_rules[current_char]
                
                # 处理向前组合
                if rule.get('combineWithPrevious') and i > 0:
                    combined_char = f"{chars[i-1]}{rule['connector']}{current_char}"
                    if combined_char in self.forward_index:
                        results.append(self._apply_variant_rules(combined_char, chars[i-2] if i > 1 else None, chars[i+1] if i < len(chars)-1 else None))
                        i += 1  # 跳过下一个字符，因为已组合
                        continue
                
                # 处理向后组合
                if rule.get('combineWithNext') and i < len(chars)-1:
                    combined_char = f"{current_char}{rule['connector']}{chars[i+1]}"
                    if combined_char in self.forward_index:
                        results.append(self._apply_variant_rules(combined_char, chars[i-1] if i > 0 else None, chars[i+2] if i < len(chars)-2 else None))
                        i += 2  # 跳过已组合的下一个字符
                        continue
            
            # 如果没有组合规则，直接查询单个字符
            if current_char in self.forward_index:
                results.append(self._apply_variant_rules(current_char, chars[i-1] if i > 0 else None, chars[i+1] if i < len(chars)-1 else None))
            
            i += 1
        
        return results if results else None
        
    def _apply_variant_rules(self, key, prev_char, next_char):
        """应用变体规则，参考app.js的getExplanation逻辑"""
        entry = self.forward_index.get(key)
        if not entry or key not in self.combine_rules:
            return entry
        
        # 检查是否有变体规则
        rule = self.combine_rules[key]
        if 'variants' in rule:
            for variant in rule['variants']:
                if variant['condition'](prev_char, next_char):
                    # 应用变体属性
                    for prop in ['GX', 'GHC', 'explanationCN', 'explanationEN']:
                        if prop in variant:
                            setattr(entry, prop, variant[prop])
                    return entry
        
        return entry
    
    def search_by_text(self, text, lang="cn"):
        """
        通过文本查询相关西夏文条目
        lang: "cn" 中文查询, "en" 英文查询
        """
        results = []
        terms = []
        
        if lang == "cn":
            # 中文查询，使用分词
            terms = [term.strip() for term in jieba.cut(text) if term.strip()]
        else:
            # 英文查询，简单分割
            terms = [term.strip() for term in re.split(r'[\s.,;]+', text) if term.strip()]
        
        for term in terms:
            result_words = self.reverse_index.get(term, [])
            for word in result_words:
                entry = self.forward_index[word]
                if entry not in results:
                    results.append(entry)
        
        # 根据查询词在解释中的出现次数排序结果
        scored_entries = []
        for entry in results:
            if lang == "cn":
                score = sum(entry.explanationCN.count(term) for term in terms)
            else:
                score = sum(entry.explanationEN.count(term) for term in terms)
            scored_entries.append( (entry, score) )
        
        # 按分数降序排序，分数相同则按条目类型排序
        sorted_entries = sorted(scored_entries, key=lambda x: (-x[1], x[0].entry_type))
        sorted_results = [entry for entry, score in sorted_entries]
        
        return sorted_results
    
    def search_contains(self, keyword, field="all"):
        """
        查找指定字段中包含关键词的所有条目
        field: "all", "cn", "en", "gx", "ghc"
        """
        results = []
        keyword = keyword.lower()
        
        for entry in self.forward_index.values():
            match = False
            
            if field in ["all", "cn"] and keyword in entry.explanationCN.lower():
                match = True
            elif field in ["all", "en"] and keyword in entry.explanationEN.lower():
                match = True
            elif field in ["all", "gx"] and keyword in entry.GX.lower():
                match = True
            elif field in ["all", "ghc"] and keyword in entry.GHC.lower():
                match = True
            elif field in ["all", "lfw"] and entry.LFW and keyword in entry.LFW.lower():
                match = True
            
            if match and entry not in results:
                results.append(entry)
        
        return results
    
    def fuzzy_search_key(self, partial_key):
        """模糊查询西夏文（包含部分匹配）"""
        results = []
        for key in self.forward_index.keys():
            if partial_key in key:
                results.append(self.forward_index[key])
        return results
    
    def get_all_keys(self):
        """获取所有西夏文词汇/字符"""
        return list(self.forward_index.keys())
    
    def get_all_keywords(self):
        """获取所有中英文关键词"""
        return list(self.reverse_index.keys())
    
    def get_stats(self):
        """获取词典统计信息"""
        word_count = 0
        character_count = 0
        unknown_count = 0
        
        for entry in self.forward_index.values():
            if entry.entry_type == "word":
                word_count += 1
            elif entry.entry_type == "character":
                character_count += 1
            else:
                unknown_count += 1
        
        return {
            "total_entries": len(self.forward_index),
            "words": word_count,
            "characters": character_count,
            "unknown_type": unknown_count,
            "keywords": len(self.reverse_index)
        }

# 安全加载双语词典的函数
def load_bilingual_dictionary(dict_file_path):
    """安全加载双语词典，确保所有必要的类在命名空间中可用"""
    try:
        return BilingualDictionary(dict_file_path)
    except Exception as e:
        logger.error(f"加载词典失败: {e}")
        raise

# TangutPlugin主类
@register("tangut", "runnel", "西夏文拟音和翻译插件", "1.7.0")
class TangutPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 获取插件目录路径
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        # 加载词典
        self.dictionary = None
        self._load_dictionary()
        # 字体路径
        self.font_path = os.path.join(self.plugin_dir, "NotoSerifTangut-Regular.ttf")
    
    def _load_dictionary(self):
        """加载JSON词典文件"""
        dict_path = os.path.join(self.plugin_dir, "dictionary.json")
        try:
            logger.info(f"尝试加载词典文件: {dict_path}")
            if os.path.exists(dict_path):
                logger.info(f"词典文件存在，大小: {os.path.getsize(dict_path)} 字节")
                # 使用专门的加载函数
                self.dictionary = load_bilingual_dictionary(dict_path)
                logger.info("西夏文字典加载成功")
                # 输出词典统计信息
                if self.dictionary:
                    stats = self.dictionary.get_stats()
                    logger.info(f"词典统计: {stats}")
            else:
                logger.error(f"词典文件不存在: {dict_path}")
        except Exception as e:
            logger.error(f"加载词典失败: {e}", exc_info=True)
            # 尝试检查JSON文件是否有效
            try:
                with open(dict_path, 'r', encoding='utf-8') as f:
                    test_data = json.load(f)
                logger.info(f"词典文件格式正确，包含 {len(test_data)} 个条目")
            except Exception as json_e:
                logger.error(f"词典文件格式错误: {json_e}", exc_info=True)
    
    @filter.command_group("tangut")
    def tangut(self):
        pass
    
    @tangut.command("gx")
    async def tangut_gx(self, event: AstrMessageEvent):
        """获取西夏文的龚勋拟音"""
        message = event.message_str or ""
        tangut_text = message[len("/tangut gx"):].strip()
        if not tangut_text:
            yield event.plain_result("用法: /tangut gx <西夏文>")
            return
        
        try:
            if not self.dictionary:
                yield event.plain_result("词典未加载成功，无法获取拟音")
                return
            
            # 使用 BilingualDictionary 获取龚勋拟音
            result = self._get_gx_pronunciation(tangut_text)
            yield event.plain_result(f"龚勋拟音: {result}")
        except Exception as e:
            logger.error(f"获取龚勋拟音失败: {e}", exc_info=True)
            yield event.plain_result(f"获取拟音失败: {str(e)}")
    
    @tangut.command("ghc")
    async def tangut_ghc(self, event: AstrMessageEvent):
        """获取西夏文的龚煌城拟音"""
        message = event.message_str or ""
        tangut_text = message[len("/tangut ghc"):].strip()
        if not tangut_text:
            yield event.plain_result("用法: /tangut ghc <西夏文>")
            return
        
        try:
            if not self.dictionary:
                yield event.plain_result("词典未加载成功，无法获取拟音")
                return
            
            # 使用 BilingualDictionary 获取龚煌城拟音
            result = self._get_ghc_pronunciation(tangut_text)
            yield event.plain_result(f"龚煌城拟音: {result}")
        except Exception as e:
            logger.error(f"获取龚煌城拟音失败: {e}", exc_info=True)
            yield event.plain_result(f"获取拟音失败: {str(e)}")
    
    @tangut.command("t2zh")
    async def tangut_t2zh(self, event: AstrMessageEvent):
        """将西夏文翻译为中文"""
        message = event.message_str or ""
        tangut_text = message[len("/tangut t2zh"):].strip()
        if not tangut_text:
            yield event.plain_result("用法: /tangut t2zh <西夏文>")
            return
        
        try:
            if not self.dictionary:
                yield event.plain_result("词典未加载成功，无法进行翻译")
                return
            
            # 使用 BilingualDictionary 获取逐字释义
            literal_meanings = self._get_literal_meanings(tangut_text)
        
            # 将逐字释义传递给LLM生成最简翻译
            llm_prompt = f"根据以下西夏文逐字释义，生成最简翻译：{literal_meanings}"
        
            # 调用LLM进行翻译
            provider = self.context.get_using_provider()
            if not provider:
                yield event.plain_result("未配置可用的语言模型")
                return
        
            llm_response = await provider.text_chat(
                prompt=llm_prompt,
                session_id=None,
                contexts=[],
                image_urls=[],
                func_tool=None,
                system_prompt="你是一个翻译助手，擅长将逐字释义转换为流畅的中文翻译。仅输出简洁明了的翻译结果，不要添加额外解释。"
            )
        
            if llm_response.role == "assistant":
                translation = llm_response.completion_text
                yield event.plain_result(f"逐字词释义:\n{literal_meanings}\n最简翻译: {translation}")
            else:
                yield event.plain_result("翻译失败: LLM返回异常")
        except Exception as e:
            logger.error(f"西夏文翻译失败: {e}", exc_info=True)
            yield event.plain_result(f"翻译失败: {str(e)}")
    
    @tangut.command("zh2t")
    async def tangut_zh2t(self, event: AstrMessageEvent):
        """将中文翻译为西夏文（实验性功能）"""
        message = event.message_str or ""
        chinese_text = message[len("/tangut zh2t"):].strip()
        if not chinese_text:
            yield event.plain_result("用法: /tangut zh2t <中文>")
            return
    
        try:
            if not self.dictionary:
                yield event.plain_result("词典未加载成功，无法进行翻译")
                return
            
            # 步骤1: 使用LLM对中文进行预处理（分词和语序调整）
            preprocessed_text = await self._preprocess_chinese(chinese_text)
            
            # 步骤2: 分词处理
            words = preprocessed_text.split()
            
            # 步骤3: 对每个词只匹配一个西夏文字符/词语
            tangut_result = ""
            for word in words:
                # 为每个词查找匹配的西夏文字符/词语
                char_result = self._find_single_tangut_char(word)
                tangut_result += char_result
            
            # 发送西夏文结果
            yield event.plain_result(f"西夏文结果: {tangut_result}")
            
            # 如果有西夏文结果，渲染为图片并发送
            if tangut_result and tangut_result != "未找到匹配的西夏文":
                image_path = self._render_tangut_text(tangut_result)
                if image_path and os.path.exists(image_path):
                    yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"中文到西夏文翻译失败: {e}", exc_info=True)
            yield event.plain_result(f"翻译失败: {str(e)}")

    def _find_single_tangut_char(self, chinese_char: str) -> str:
        # 直接查询
        results = self.dictionary.search_by_text(chinese_char)
        if results:
            if isinstance(results, list):
                # 按字符数升序排序，取最短匹配
                sorted_results = sorted(results, key=lambda x: len(x.key))
                return sorted_results[0].key
            return results.key if hasattr(results, 'key') else list(results.keys())[0]

        # 拆分单字查询
        tangut_parts = []
        for char in chinese_char:
            # 优先查询包含该字的单字符条目
            single_results = self.dictionary.search_contains(char, field='cn')
            if single_results:
                if isinstance(single_results, list):
                    # 过滤单字符结果并按字符数排序
                    single_char_results = [r for r in single_results if len(r.key) == 1]
                    if single_char_results:
                        tangut_parts.append(sorted(single_char_results, key=lambda x: len(x.key))[0].key)
                        continue
                elif len(single_results.key) == 1:
                    tangut_parts.append(single_results.key)
                    continue
            tangut_parts.append('𗸠')
        
        return ''.join(tangut_parts) if any(tangut_parts) else '𗸠'
    
    @tangut.command("render")
    async def tangut_render(self, event: AstrMessageEvent):
        """将西夏文渲染为图片"""
        message = event.message_str or ""
        tangut_text = message[len("/tangut render"):].strip()
        if not tangut_text:
            yield event.plain_result("用法: /tangut render <西夏文>")
            return
        
        try:
            # 渲染西夏文为图片
            image_path = self._render_tangut_text(tangut_text)
            
            if image_path and os.path.exists(image_path):
                yield event.image_result(image_path)
                os.remove(image_path)
            else:
                yield event.plain_result("西夏文渲染失败")
        except Exception as e:
            logger.error(f"西夏文渲染失败: {e}", exc_info=True)
            yield event.plain_result(f"渲染失败: {str(e)}")
    
    async def _preprocess_chinese(self, chinese_text):
        """使用LLM预处理中文文本"""
        llm_prompt = f"""
        请将以下中文文本进行分词，并调整为藏缅语序（通常是宾语在前，动词在后）并尽可能把用词改成常用词，生僻词语直接进行近义词替换：
        {chinese_text}
        输出格式：分词后的词用空格分隔，不需要解释。仅给出最终结果，不要显示任何中间步骤。
        """
        # 调用LLM进行预处理
        provider = self.context.get_using_provider()
        if not provider:
            raise Exception("未配置可用的语言模型")

        llm_response = await provider.text_chat(
            prompt=llm_prompt,
            session_id=None,
            contexts=[],
            image_urls=[],
            func_tool=None,
            system_prompt="你是一个文本处理器，擅长中文分词和语序调整。请严格按照要求输出，不要添加额外解释。"
        )

        if llm_response.role == "assistant":
            return llm_response.completion_text.strip()
        else:
            raise Exception
    
    def _get_gx_pronunciation(self, tangut_text):
        """获取龚勋拟音"""
        pronunciations = []
        for char in tangut_text:
            result = self.dictionary.search_by_key(char)
            if result:
                # 处理结果可能是单个条目或条目列表
                if isinstance(result, list):
                    # 取第一个匹配项的GX拟音
                    gx = result[0].GX if result[0] and result[0].GX else char
                else:
                    gx = result.GX if result and result.GX else char
                pronunciations.append(gx)
            else:
                pronunciations.append(char)
        return " ".join(pronunciations)
    
    def _get_ghc_pronunciation(self, tangut_text):
        """获取龚煌城拟音"""
        pronunciations = []
        for char in tangut_text:
            result = self.dictionary.search_by_key(char)
            if result:
                # 处理结果可能是单个条目或条目列表
                if isinstance(result, list):
                    # 取第一个匹配项的GHC拟音
                    ghc = result[0].GHC if result[0] and result[0].GHC else char
                else:
                    ghc = result.GHC if result and result.GHC else char
                pronunciations.append(ghc)
            else:
                pronunciations.append(char)
        return " ".join(pronunciations)
    
    def _get_literal_meanings(self, tangut_text):
        """获取逐字释义（改进版，支持词组优先和字符组合规则）"""
        # 初始化结果数组
        meanings = []
        i = 0
        text_length = len(tangut_text)
        
        # 词组优先匹配逻辑
        while i < text_length:
            current_char = tangut_text[i]
            matched = False
            
            # 首先尝试匹配词组（最长匹配优先）
            # 尝试查找最长可能的词组（最多5个字符，防止过度匹配）
            max_word_length = min(5, text_length - i)
            found_word = None
            
            for word_length in range(max_word_length, 1, -1):
                candidate = tangut_text[i:i+word_length]
                # 使用search_by_text查找词组
                word_result = self.dictionary.search_by_text(candidate)
                
                if word_result:
                    # 如果结果是列表，检查是否有完全匹配项
                    if isinstance(word_result, list):
                        for item in word_result:
                            if hasattr(item, 'key') and item.key == candidate:
                                found_word = item
                                break
                    # 如果结果是字典，直接检查key
                    elif hasattr(word_result, 'key') and word_result.key == candidate:
                        found_word = word_result
                    
                    if found_word:
                        meaning = found_word.explanationCN if hasattr(found_word, 'explanationCN') and found_word.explanationCN else candidate
                        meanings.append(meaning)
                        i += word_length
                        matched = True
                        break
            
            # 如果没有匹配到词组，处理单个字符
            if not matched:
                # 获取前后字符作为上下文
                prev_char = tangut_text[i-1] if i > 0 else None
                next_char = tangut_text[i+1] if i < text_length - 1 else None
                
                # 查询单个字符
                result = self.dictionary.search_by_key(current_char)
                
                if result:
                    # 处理结果可能是单个条目或条目列表
                    if isinstance(result, list):
                        # 取第一个匹配项的中文解释
                        meaning = result[0].explanationCN if result[0] and hasattr(result[0], 'explanationCN') and result[0].explanationCN else current_char
                    else:
                        meaning = result.explanationCN if hasattr(result, 'explanationCN') and result.explanationCN else current_char
                    meanings.append(meaning)
                else:
                    meanings.append(current_char)
                
                i += 1
        
        return "    ".join(meanings)
    
    def _find_tangut_by_chinese(self, chinese_text):
        """根据中文文本查找西夏文"""
        # 使用search_by_text进行反向查询
        results = self.dictionary.search_by_text(chinese_text, lang="cn")
        
        if not results:
            return "未找到匹配的西夏文"
        
        # 提取西夏文字符
        tangut_chars = []
        for entry in results[:10]:  # 限制返回结果数量
            if hasattr(entry, 'key'):
                tangut_chars.append(entry.key)
        
        # 去重并保持顺序
        seen = set()
        unique_chars = [char for char in tangut_chars if not (char in seen or seen.add(char))]
        
        return "".join(unique_chars[:20]) 
    
    def _render_tangut_text(self, tangut_text):
        """将西夏文文本渲染为图片"""
        try:
            font_size = 60
            
            if not os.path.exists(self.font_path):
                logger.error(f"字体文件不存在: {self.font_path}")
                return None
            
            font = ImageFont.truetype(self.font_path, font_size)

            bbox = font.getbbox(tangut_text)
            text_width = bbox[2] - bbox[0]  # right - left
            text_height = bbox[3] - bbox[1]  # bottom - top

            padding = 20
            image_width = text_width + padding * 2
            image_height = text_height + padding * 2
            
            image = Image.new('RGBA', (image_width, image_height), (255, 255, 255, 255))
            draw = ImageDraw.Draw(image)
    
            draw.text((padding, padding), tangut_text, font=font, fill=(0, 0, 0, 255))
            
            temp_dir = os.path.join(self.plugin_dir, "temp")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            image_path = os.path.join(temp_dir, f"tangut_render_{hash(tangut_text)}.png")
            image.save(image_path, "PNG")
            
            return image_path
        except Exception as e:
            logger.error(f"渲染西夏文失败: {e}", exc_info=True)
            return None