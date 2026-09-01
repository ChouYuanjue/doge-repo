from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.builtin_stars.builtin_commands.commands import (
    AdminCommands,
    ConversationCommands,
    NameCommand,
    ProviderCommands,
    SetUnsetCommands,
    SIDCommand,
)
from astrbot.core.star.filter.command import GreedyStr


@register("doge_admin", "runnel", "AstrBot 默认命令的 /admin 命名空间", "5.5.0")
class DogeAdmin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.admin_c = AdminCommands(context)
        self.conversation_c = ConversationCommands(context)
        self.name_c = NameCommand(context)
        self.provider_c = ProviderCommands(context)
        self.setunset_c = SetUnsetCommands(context)
        self.sid_c = SIDCommand(context)

    @filter.command_group("admin")
    def admin(self):
        """AstrBot framework/default commands."""

    @admin.command("help")
    async def help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "AstrBot framework commands\n"
            "/admin sid\n"
            "/admin reset · /admin stop · /admin new · /admin stats\n"
            "/admin set <key> <value> · /admin unset <key>\n"
            "/admin name <alias> [admin]\n"
            "/admin provider [index] [model-index] [admin]\n"
            "/admin dashboard_update [admin]"
        )

    @admin.command("sid")
    async def sid(self, event: AstrMessageEvent):
        await self.sid_c.sid(event)

    @admin.command("reset")
    async def reset(self, event: AstrMessageEvent):
        await self.conversation_c.reset(event)

    @admin.command("stop")
    async def stop(self, event: AstrMessageEvent):
        await self.conversation_c.stop(event)

    @admin.command("new")
    async def new_conv(self, event: AstrMessageEvent):
        await self.conversation_c.new_conv(event)

    @admin.command("stats")
    async def stats(self, event: AstrMessageEvent):
        await self.conversation_c.stats(event)

    @admin.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: GreedyStr):
        await self.setunset_c.set_variable(event, key, str(value))

    @admin.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str):
        await self.setunset_c.unset_variable(event, key)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @admin.command("name")
    async def name(self, event: AstrMessageEvent, alias: GreedyStr):
        await self.name_c.name(event, str(alias))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @admin.command("provider")
    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ):
        await self.provider_c.provider(event, idx, idx2)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @admin.command("dashboard_update")
    async def dashboard_update(self, event: AstrMessageEvent):
        await self.admin_c.update_dashboard(event)
