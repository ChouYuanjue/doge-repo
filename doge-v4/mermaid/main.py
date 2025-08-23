from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.core.star.register import register_llm_tool as llm_tool
from astrbot.core import AstrBotConfig
import astrbot.api.message_components as Comp

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
import uuid
import os

import mermaid as md
from mermaid.graph import Graph

@register("mermaid", "kterna", "使用Mermaid语法生成各种图表（思维导图、流程图、时序图等）", "1.3.0", "https://github.com/kterna/astrbot_plugin_mermaid")
class MermaidPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        os.environ['MERMAID_INK_SERVER'] = config.get("MERMAID_INK_SERVER")
        super().__init__(context)
        # 在插件目录下创建temp文件夹
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_dir = os.path.join(plugin_dir, "temp")
        # 确保temp目录存在
        os.makedirs(self.temp_dir, exist_ok=True)
        # 创建线程池
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.system_prompt = """
您是一名首席设计师，负责使用 Mermaid.js 根据用户提出的要求详细的创建对应的mermaid图表。您的目标是准确地表示解释中描述的项目的架构和设计。
要创建 Mermaid.js 图表：
1.仔细阅读用户提出的要求，理解用户的需求。
2.根据用户的需求，使用Mermaid.js的语法，创建对应的mermaid图表。
3.确保图表的准确性和完整性。
4.确保图表的清晰性和可读性。
5.确保图表的简洁性和美观性。

图表组件和关系的指南：
- 为不同类型的组件使用适当的形状（例如，服务的矩形，数据库的圆柱体等）
- 为每个组件使用清晰简洁的标签
- 使用箭头显示数据流或依赖关系的方向
- 如果适用，将相关组件分组在一起
- 包括解释中提到的任何重要注释或批注
- 只需遵循解释。它将拥有您需要的一切。

重要提示！！：请尽可能垂直地定位和绘制图表。您必须避免节点和部分的水平长列表！

极其重要的语法注意事项！！！（请注意）：
- 确保为图表添加颜色！！！这非常关键。
- 在 Mermaid.js 语法中，我们不能在没有引号的情况下为节点包含特殊字符！例如：`EX[/api/process (Backend)]:::api` 和 `API -->|calls Process()| Backend` 是语法错误的两个示例。它们应该是 `EX["/api/process (Backend)"]:::api` 和 `API -->|"calls Process()"| Backend`。请注意引号。这非常重要。确保为包含特殊字符的任何字符串添加引号。
- 在 Mermaid.js 语法中，您不能直接在子图声明中应用类样式。例如：`subgraph "Frontend Layer":::frontend` 是语法错误。但是，您可以将它们应用于子图中的节点。例如：`Example["Example Node"]:::frontend` 是有效的，并且 `class Example1,Example2 frontend` 是有效的。
- 在 Mermaid.js 语法中，关系标签名称中不能有空格。例如：`A -->| "example relationship" | B` 是语法错误。它应该是 `A -->|"example relationship"| B`
- 在 Mermaid.js 语法中，您不能像节点一样为子图提供别名。例如：`subgraph A "Layer A"` 是语法错误。它应该是 `subgraph "Layer A"`
"""
    
    @filter.command("mermaid")
    async def mermaid_command(self, event: AstrMessageEvent):
        '''生成Mermaid图表，使用方法: /mermaid 提示词'''
        # 获取提示词
        prompt = event.message_str.replace("/mermaid", "", 1).strip()
        if not prompt:
            yield event.plain_result("请提供提示词以生成图表，例如：/mermaid 创建一个展示项目开发流程的流程图")
            return
        
        # 向用户发送处理中的消息
        yield event.plain_result("🔄 正在为您生成图表，请稍候...")
        
        # 使用LLM生成图表
        system_prompt = self.system_prompt

        user_prompt = f"请为我创建一个关于'{prompt}'的图表，直接提供Mermaid代码块，以```mermaid开头，以```结尾。"
        
        # 调用LLM
        llm_response = await self.context.get_using_provider().text_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        
        # 提取LLM返回的文本内容
        text = getattr(llm_response, "completion_text", "")
        if not text:
            yield event.plain_result("❌ 生成图表失败：无法获取LLM响应内容")
            return

        # 处理文本和代码块
        result_chain = await self.process_text_with_mermaid(text)
        if not result_chain:
            yield event.plain_result("❌ 未能在LLM响应中找到有效的Mermaid代码")
            return
            
        yield event.chain_result(result_chain)
    
    @llm_tool(name="generate_mermaid")
    async def generate_mermaid(self, event: AstrMessageEvent, keywords: str) -> MessageEventResult:
        '''生成Mermaid图表。根据关键词创建流程图、思维导图、时序图等。

        Args:
            keywords(string): 图表主题关键词
        '''
        if not isinstance(keywords, str) or not keywords:
            yield event.plain_result("❌ 请提供有效的图表主题")
            return
        
        # 重用现有的mermaid_command逻辑
        prompt = keywords
        # 向用户发送处理中的消息
        yield event.plain_result("🔄 正在为您生成图表，请稍候...")
        
        # 使用LLM生成图表
        system_prompt = self.system_prompt
        user_prompt = f"请为我创建一个关于'{prompt}'的图表，直接提供Mermaid代码块，以```mermaid开头，以```结尾。"
        
        # 调用LLM
        llm_response = await self.context.get_using_provider().text_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        
        # 提取LLM返回的文本内容
        text = getattr(llm_response, "completion_text", "")
        if not text:
            yield event.plain_result("❌ 生成图表失败：无法获取LLM响应内容")
            return

        # 处理文本和代码块
        result_chain = await self.process_text_with_mermaid(text)
        if not result_chain:
            yield event.plain_result("❌ 未能在LLM响应中找到有效的Mermaid代码")
            return
            
        yield event.chain_result(result_chain)
    
    async def process_text_with_mermaid(self, text: str) -> list:
        '''处理文本，提取并转换Mermaid代码块'''
        import re
        
        result_chain = []
        # 分割文本以找到代码块
        # 匹配```mermaid和```之间的内容，或者```和```之间的内容
        mermaid_pattern = r'```mermaid\s*([\s\S]*?)\s*```'
        code_pattern = r'```\s*([\s\S]*?)\s*```'
        
        last_end = 0
        
        # 首先尝试匹配```mermaid代码块
        for match in re.finditer(mermaid_pattern, text):
            # 添加代码块前的文本
            if match.start() > last_end:
                pre_text = text[last_end:match.start()].strip()
                if pre_text:
                    result_chain.append(Comp.Plain(text=pre_text))
            
            # 提取并转换Mermaid代码
            mermaid_code = match.group(1).strip()
            if mermaid_code:
                # 生成图表
                mermaid_result = await self.mermaid2image(mermaid_code)
                result_chain.extend(mermaid_result)
            
            last_end = match.end()
        
        # 如果没有找到```mermaid代码块，尝试匹配普通代码块，并检查它是否可能是Mermaid代码
        if last_end == 0:
            for match in re.finditer(code_pattern, text):
                # 添加代码块前的文本
                if match.start() > last_end:
                    pre_text = text[last_end:match.start()].strip()
                    if pre_text:
                        result_chain.append(Comp.Plain(text=pre_text))
                
                # 提取代码
                code = match.group(1).strip()
                # 检查是否可能是Mermaid代码（包含常见的Mermaid关键字）
                mermaid_keywords = ['graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 
                                   'stateDiagram', 'erDiagram', 'journey', 'gantt', 'pie', 'mindmap']
                is_mermaid = any(keyword in code.lower() for keyword in mermaid_keywords)
                
                if is_mermaid:
                    # 生成图表
                    mermaid_result = await self.mermaid2image(code)
                    result_chain.extend(mermaid_result)
                else:
                    # 作为普通代码块保留
                    result_chain.append(Comp.Plain(text=f"```\n{code}\n```"))
                
                last_end = match.end()
        
        # 添加剩余文本
        if last_end < len(text):
            remaining_text = text[last_end:].strip()
            if remaining_text:
                result_chain.append(Comp.Plain(text=remaining_text))
        
        return result_chain
        
    async def mermaid2image(self, mermaid_code: str) -> list:
        '''将Mermaid语法转换为图像。'''
        max_retries = 3
        retry_count = 0
        base_delay = 1  # 基础延迟1秒
        
        # 生成唯一文件名使用UUID而不是hash
        img_id = uuid.uuid4().hex
        img_path = os.path.join(self.temp_dir, f"mermaid_{img_id}.png")
        
        while retry_count <= max_retries:
            try:                
                # 创建图表并渲染
                graph = Graph("Mermaid图表", mermaid_code)
                render = md.Mermaid(graph)
                
                # 异步执行图表生成
                await asyncio.get_event_loop().run_in_executor(
                    self.executor, 
                    functools.partial(render.to_png, img_path)
                )
                
                # 检查文件是否成功生成
                if not os.path.exists(img_path):
                    raise Exception("图像文件生成失败")
                
                # 验证生成的文件是否为有效的PNG图像
                file_size = os.path.getsize(img_path)
                if file_size < 1024:  # 小于1KB，可能是错误文件
                    # 读取文件内容
                    with open(img_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read().lower()
                    
                    # 检查错误类型
                    import re
                    # 如果是网络错误且还有重试次数，则重试
                    if re.search(r'unknown|network|fail|server', content) and retry_count < max_retries:
                        retry_count += 1
                        # 指数退避延迟
                        delay = base_delay * (2 ** (retry_count - 1))
                        await asyncio.sleep(delay)
                        continue
                    
                    # 清理错误文件
                    self._clean_file(img_path)
                    
                    error_message = "生成图表失败"
                    if re.search(r'unknown|network|fail|server', content):
                        error_message = f"❌ 生成图表失败：出现网络或服务器错误 (已重试{retry_count}次)"
                    elif re.search(r'parse|syntax|invalid|expect', content):
                        error_message = "❌ 生成图表失败：Mermaid语法错误，请检查图表代码"
                    else:
                        error_message = f"❌ 生成图表失败：{content[:100]}..."
                    
                    return [Comp.Plain(text=error_message)]
                
                # 获取响应结果
                response = [
                    Comp.Plain(text="✅ 图表生成成功:\n"),
                    Comp.Image(file=img_path)
                ]
                
                # 标记此文件为待清理状态
                self._schedule_file_cleanup(img_path)
                
                return response
                
            except Exception as e:
                # 确保清理可能部分生成的文件
                if os.path.exists(img_path):
                    self._clean_file(img_path)
                    
                error_msg = str(e).lower()
                # 检查是否是网络连接相关错误
                if (any(network_err in error_msg for network_err in ["connection", "timeout", "network", "server"]) 
                    and retry_count < max_retries):
                    retry_count += 1
                    delay = base_delay * (2 ** (retry_count - 1))
                    await asyncio.sleep(delay)
                    continue
                
                return [Comp.Plain(text=f"❌ 生成图表时发生错误: {str(e)}\n请检查Mermaid语法是否正确，或尝试简化图表内容。")]
        
        # 如果重试全部失败
        return [Comp.Plain(text=f"❌ 生成图表失败：服务器连接问题，已尝试重试{max_retries}次")]
    
    def _clean_file(self, file_path):
        """立即清理文件的辅助方法"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            # 记录错误但不抛出异常
            print(f"清理文件 {file_path} 失败: {str(e)}")
    
    def _schedule_file_cleanup(self, file_path, delay_seconds=300):
        """安排延迟清理文件"""
        async def delayed_cleanup():
            try:
                # 等待指定时间以确保文件已被使用
                await asyncio.sleep(delay_seconds)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"已清理临时文件: {os.path.basename(file_path)}")
            except Exception as e:
                print(f"延迟清理文件 {file_path} 失败: {str(e)}")
                
        # 创建异步任务来执行延迟清理
        asyncio.create_task(delayed_cleanup())