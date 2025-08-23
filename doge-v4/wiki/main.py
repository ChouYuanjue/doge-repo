
import uuid
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.api import logger
from .deepwiki import DeepWikiClient


@register(
    "astrbot_plugin_deepwiki",
    "Zhalslar",
    "使用deepwiki查询指定github仓库，可作为问答助手",
    "1.0.1",
    "https://github.com/Zhalslar/astrbot_plugin_deepwiki",
)
class DeepWikiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.default_repo_name = "ChouYuanjue/doge-repo"
        self.client = DeepWikiClient()

    @filter.command("deepwiki", alias={"dw","wiki"})
    async def deepwiki(self, event: AstrMessageEvent, repo_name: str):
        try:
            args = event.message_str.removeprefix("deepwiki").removeprefix("dw").removeprefix("wiki").strip().split(" ")
            if len(args) <= 1:
                repo_name = self.default_repo_name
                user_prompt = " ".join(args)
            else:
                repo_name = args[0]
                user_prompt = " ".join(args[1:])
            query_id = str(uuid.uuid4())
            logger.debug(f"repo_name: {repo_name}, user_prompt: {user_prompt}, query_id: {query_id}")
            result = await self.client.query(repo_name, user_prompt, query_id)
            image = await self.text_to_image(result["chat_results"])
            yield event.image_result(image)
        except Exception as e:
            yield event.plain_result("查询失败")
            logger.error(f"\n❌ 查询失败：{str(e)}")
