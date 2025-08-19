#未知作者（可能是AI）写的插件，仅仅稍作修改以增加渲染结果的美观度

import asyncio
import os
import shutil # 用于清理临时目录
import uuid
import re # 用于自动检测的正则表达式
from html import unescape # 用于解码HTML实体

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult # 导入事件相关API
from astrbot.api.star import Context, Star, register # 导入插件基类和注册器
from astrbot.api import logger as astrbot_logger # 使用 AstrBot 的 logger
import astrbot.api.message_components as Comp # 导入消息组件

# 假设 latex_renderer.py 与 main.py 在同一目录下
from . import latex_renderer # 使用相对导入，导入LaTeX渲染核心逻辑

# --- 插件元数据 ---
PLUGIN_NAME = "doge_latex" 
PLUGIN_AUTHOR = "runnel" 
PLUGIN_DESCRIPTION = "通过matplotlib的mathtext渲染latex公式"
PLUGIN_VERSION = "1.0.0" 

# --- 默认配置 ---
DEFAULT_DPI = 300
DEFAULT_FONTSIZE = 18
DEFAULT_BGCOLOR = 'white'
DEFAULT_FGCOLOR = 'black'
DEFAULT_MAX_DELIMITER_HEIGHT = 2
DEFAULT_AUTOCROP_PADDING = 0 
DEFAULT_STITCH_LINE_SPACING = 5 # 默认拼接行间距

# 自动检测LaTeX的正则表达式 (基础示例)
AUTO_DETECT_PATTERN = re.compile(
    r"(\${1,2}[^$]+\${1,2}(?:\s*,\s*\${1,2}[^$]+\${1,2})*)|" # $..$, $$..$$
    # 匹配类似 A=B, C=D 的结构，允许更复杂的LHS和RHS
    r"([\w\s\+\-\*\/=\(\)\^\_\{\}\\]+(?:\\(?:frac|sqrt|sum|int|lim|text)\{[^}]*\}\{[^}]*\}|\\(?:sin|cos|tan|log|ln))?[\w\s\+\-\*\/=\(\)\^\_\{\}\\]*\s*=\s*[^,]+(?:,\s*[\w\s\+\-\*\/=\(\)\^\_\{\}\\]+(?:\\(?:frac|sqrt|sum|int|lim|text)\{[^}]*\}\{[^}]*\}|\\(?:sin|cos|tan|log|ln))?[\w\s\+\-\*\/=\(\)\^\_\{\}\\]*\s*=\s*[^,]+)*)"
)
AUTO_DETECT_DELIMITER = ','

@register(PLUGIN_NAME, PLUGIN_AUTHOR, PLUGIN_DESCRIPTION, PLUGIN_VERSION)
class LaTeXRendererPlugin(Star): 
    def __init__(self, context: Context, config=None): 
        super().__init__(context) 
        if isinstance(config, dict):
            self.config = config
            astrbot_logger.info(f"插件 {PLUGIN_NAME} 使用提供的配置进行初始化。")
        else:
            self.config = {} 
            if config is not None: 
                astrbot_logger.warning(f"插件 {PLUGIN_NAME} 初始化时收到非预期的配置类型: {type(config)}。将使用默认空配置。")
            else:
                astrbot_logger.info(f"插件 {PLUGIN_NAME} 未提供配置，使用默认空配置进行初始化。")
        
        astrbot_logger.debug(f"插件 {PLUGIN_NAME} 初始化完成。self 类型: {type(self)}, self.config 类型: {type(self.config)}")

        # 使用相对路径 "data" 作为基础，并为插件数据创建子目录
        self.base_data_dir = "data" # AstrBot 的主数据目录名
        self.plugin_specific_data_dir = os.path.join(self.base_data_dir, "plugin_data", PLUGIN_NAME)
        self.temp_image_dir = os.path.join(self.plugin_specific_data_dir, "temp_images")
        
        # 确保所有需要的目录都存在
        if not os.path.exists(self.plugin_specific_data_dir):
            os.makedirs(self.plugin_specific_data_dir, exist_ok=True)
        if not os.path.exists(self.temp_image_dir):
            os.makedirs(self.temp_image_dir, exist_ok=True)
            
        astrbot_logger.info(f"插件 {PLUGIN_NAME} 的临时图片目录设置为: {os.path.abspath(self.temp_image_dir)}")

        # 从配置加载参数
        self.dpi = self.config.get("dpi", DEFAULT_DPI)
        self.fontsize = self.config.get("fontsize", DEFAULT_FONTSIZE)
        self.bgcolor = self.config.get("bgcolor", DEFAULT_BGCOLOR)
        self.fgcolor = self.config.get("fgcolor", DEFAULT_FGCOLOR)
        self.max_delimiter_height = self.config.get("max_delimiter_height", DEFAULT_MAX_DELIMITER_HEIGHT)
        self.autocrop_padding = self.config.get("autocrop_padding", DEFAULT_AUTOCROP_PADDING)
        self.stitch_line_spacing = self.config.get("stitch_line_spacing", DEFAULT_STITCH_LINE_SPACING)
        self.enable_auto_render = self.config.get("enable_auto_render", False) 
        self.auto_render_delimiter = self.config.get("auto_render_delimiter", AUTO_DETECT_DELIMITER)


    async def _render_and_send(self, event: AstrMessageEvent, latex_input: str, delimiter: str):
        """
        内部辅助函数，用于渲染LaTeX并发送结果。
        """
        astrbot_logger.debug(f"进入 _render_and_send。原始 latex_input: '{latex_input}', 分隔符: '{delimiter}'")

        if not latex_input or not latex_input.strip(): 
            yield event.plain_result("LaTeX 内容不能为空。") 
            return

        cleaned_latex_input = unescape(latex_input.strip()) 
        astrbot_logger.debug(f"_render_and_send：清理后的 cleaned_latex_input: '{cleaned_latex_input}'")

        output_filename_base = f"latex_render_{uuid.uuid4().hex}.png"
        output_filepath = os.path.join(self.temp_image_dir, output_filename_base)

        try:
            astrbot_logger.info(f"准备调用核心渲染程序处理 LaTeX (前200字符): {cleaned_latex_input[:200]}...") 
            loop = asyncio.get_event_loop() 
            await loop.run_in_executor(
                None, 
                latex_renderer.process_and_render_latex, 
                cleaned_latex_input, 
                output_filepath,
                delimiter, 
                self.dpi,
                self.fontsize,
                self.bgcolor,
                self.fgcolor,
                self.autocrop_padding,
                self.max_delimiter_height,
                True, # cleanup_temp_files for process_and_render_latex's internal temps
                self.stitch_line_spacing # 传递行间距参数
            )

            if os.path.exists(output_filepath): 
                astrbot_logger.info(f"LaTeX 渲染成功，图片保存在: {output_filepath}")
                yield event.image_result(output_filepath) 
            else:
                astrbot_logger.error(f"LaTeX 渲染声称成功，但未找到输出文件: {output_filepath}")
                yield event.plain_result("抱歉，LaTeX 渲染失败了（未生成图片）。")

        except Exception as e: 
            astrbot_logger.error(f"LaTeX 渲染过程中发生错误: {e}", exc_info=True) 
            yield event.plain_result(f"抱歉，LaTeX 渲染失败了：{str(e)[:100]}") 
        finally:
            # 考虑是否在此处或terminate中清理 output_filepath
            # 如果发送后立即删除，可能会导致某些平台无法及时获取图片
            pass

    @filter.command("latex", alias={"tex", "renderlatex"})
    async def handle_manual_latex_render(self, event: AstrMessageEvent, _first_word_after_command: str):
        """
        手动渲染LaTeX指令。
        用法: /latex <你的LaTeX代码>
        或者 /tex <你的LaTeX代码>
        """
        
        full_message = event.message_str.strip() 
        astrbot_logger.debug(f"handle_manual_latex_render: 接收到的完整消息 (event.message_str): '{full_message}'")

        command_to_check = ""
        actual_command_len = 0 

        # 检查可能的命令及其别名 (不带斜杠)，并确保命令后有空格
        possible_commands_with_space = [cmd + " " for cmd in ["latex", "tex", "renderlatex"]]
        
        for cmd_with_space in possible_commands_with_space:
            if full_message.lower().startswith(cmd_with_space):
                command_to_check = cmd_with_space
                actual_command_len = len(command_to_check)
                break 
        
        content_part = ""
        if actual_command_len > 0:
            content_part = full_message[actual_command_len:].strip()
            astrbot_logger.info(f"handle_manual_latex_render: 成功分离命令 '{command_to_check.strip()}'。提取的 latex_content: '{content_part}'")
        else:
            astrbot_logger.warning(f"无法从消息 '{full_message}' 中通过已知命令前缀分离内容。请检查命令格式。")
            yield event.plain_result("无法解析命令或提取LaTeX内容。请确保命令后有空格和内容，例如: /latex E=mc^2")
            return

        if not content_part: 
            yield event.plain_result("请提供LaTeX内容。用法: /latex <内容>")
            return

        astrbot_logger.info(f"最终用于渲染的 LaTeX 内容 (前100字符): {content_part[:100]}...")
        manual_command_delimiter = self.config.get("manual_command_delimiter", ",")
        
        async for result in self._render_and_send(event, content_part, manual_command_delimiter):
            yield result
        event.stop_event() 


    async def auto_render_latex_on_message(self, event: AstrMessageEvent):
        """
        自动检测消息中的LaTeX结构并渲染。
        此功能默认关闭，可以通过插件配置开启。
        """
        if not self.enable_auto_render: 
            return 
        if event.message_str.startswith('/'): 
            return
        
        message_text = event.message_str.strip()
        match = AUTO_DETECT_PATTERN.search(message_text) 
        
        if match:
            latex_to_render = next((g for g in match.groups() if g is not None), None) 
            if latex_to_render:
                if AUTO_DETECT_DELIMITER in latex_to_render or \
                   '\\' in latex_to_render or \
                   '$' in latex_to_render: 
                    astrbot_logger.info(f"自动检测到潜在LaTeX内容: {latex_to_render[:100]}...")
                    async for result in self._render_and_send(event, latex_to_render, self.auto_render_delimiter):
                        yield result
                    event.stop_event() 


    async def terminate(self):
        """
        插件卸载/停用时调用，用于清理资源。
        """
        astrbot_logger.info(f"插件 {PLUGIN_NAME} 正在终止，清理临时图片目录: {self.temp_image_dir}")
        if os.path.exists(self.temp_image_dir):
            try:
                shutil.rmtree(self.temp_image_dir) 
                astrbot_logger.info(f"临时图片目录 {self.temp_image_dir} 已成功删除。")
            except Exception as e:
                astrbot_logger.error(f"删除临时图片目录 {self.temp_image_dir} 失败: {e}", exc_info=True)
        return await super().terminate()

