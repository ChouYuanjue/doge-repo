from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger
import json
import os
import random
from typing import Optional

@register("wp", "runnel", "弱能力获取与对战插件", "1.0.0")
class WpPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        self.user_data_dir = os.path.join(os.path.dirname(__file__), "user_data")
        os.makedirs(self.user_data_dir, exist_ok=True)
        
        self.wp_data = self.load_wp_data()
    
    def load_wp_data(self):
        wp_file = os.path.join(os.path.dirname(__file__), "wp.json")
        try:
            with open(wp_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error("wp.json文件未找到")
            return []
        except json.JSONDecodeError:
            logger.error("wp.json格式错误")
            return []
    
    def get_user_file_path(self, user_id: str) -> str:
        return os.path.join(self.user_data_dir, f"{user_id}.json")
    
    def save_user_data(self, user_id: str, user_name: str, power_name: str, power_desc: str):
        user_data = {
            "user_id": user_id,
            "user_name": user_name,
            "power_name": power_name,
            "power_desc": power_desc
        }
        
        user_file = self.get_user_file_path(user_id)
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
    
    def load_user_data(self, user_id: str) -> Optional[dict]:
        user_file = self.get_user_file_path(user_id)
        if not os.path.exists(user_file):
            return None
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    
    @filter.command_group("wp")
    def wp(self):
        pass

    @wp.command("get")
    async def wp_get(self, event: AstrMessageEvent):
        if not self.wp_data:
            yield event.plain_result("能力数据加载失败，请联系管理员")
            return
        
        power = random.choice(self.wp_data)
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        self.save_user_data(user_id, user_name, power["name"], power["description"])
        
        yield event.plain_result(
            f'恭喜你成为"{power["name"]}"！\n你的能力：{power["description"]}'
        )
    
    @wp.command("fight")
    async def wp_fight(self, event: AstrMessageEvent):
        target_id = None
    
        for segment in event.message_obj.message:
            if isinstance(segment, Comp.At):
                target_id = str(segment.qq)
                break
    
        if target_id is None:
            message_str = event.message_str
            parts = message_str.split()
            if len(parts) > 2:
                target_id = parts[2] 
                
        if not target_id:
            yield event.plain_result("请指定对战目标，例如：/wp fight @某人")
            return

        user_id = event.get_sender_id()
        user_data = self.load_user_data(user_id)
        target_data = self.load_user_data(target_id)
    
        if not user_data:
            yield event.plain_result("你还没有获取能力，请先使用/wp get获取能力")
            
    
        if not target_data:
            yield event.plain_result("对战目标还没有获取能力")
            return
    
        prompt = f"""
        现在要进行一场奇幻对决：
        
        {user_data['user_name']}（{user_data['power_name']}）：
        {user_data['power_desc']}
        
        VS
        
        {target_data['user_name']}（{target_data['power_name']}）：
        {target_data['power_desc']}
        
        请描述这场对决的精彩过程（约200字），包括：
        1. 双方如何运用自己的能力
        2. 战斗的精彩瞬间
        3. 最终结果和胜者
        
        请用生动而严肃的语言描述：
        """
        
        try:
            provider = self.context.get_using_provider()
            if not provider:
                yield event.plain_result("未配置可用的语言模型")
                return
            
            llm_response = await provider.text_chat(
                prompt=prompt,
                session_id=None,
                contexts=[],
                image_urls=[],
                func_tool=None,
                system_prompt="你是一个对决的观察员，擅长用严肃专业的语言对战斗场面进行总结，语气平静。你不应当使用任何markdown语法。回复纯文本。"
            )
            
            # 发送结果
            if llm_response.role == "assistant":
                yield event.plain_result(llm_response.completion_text)
            else:
                yield event.plain_result("对决解说生成失败")
                
        except Exception as e:
            logger.error(f"调用LLM时出错: {str(e)}")
            yield event.plain_result("对决过程中发生了意外，请稍后再试")

async def terminate(self):
    pass