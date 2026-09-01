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

from data.plugins.doge_shared.module_control import (
    is_group_admin,
    list_modules,
    reset_modules,
    set_module_enabled,
)


@register("doge_admin", "runnel", "AstrBot 默认命令的 /admin 命名空间", "5.6.0")
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
            "/admin dashboard_update [admin]\n"
            "/admin modules list|on <module>|off <module>|reset  [group admin]"
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

    async def _require_group_admin(self, event: AstrMessageEvent) -> None:
        if not event.get_group_id():
            raise PermissionError("模块热插拔只在群聊中提供")
        if not await is_group_admin(event):
            raise PermissionError("只有当前群的群主或群管理员可以修改模块")

    @admin.command_group("modules")
    def modules(self):
        """AstrBot native per-session plugin switches for the current group."""

    @modules.command("list")
    async def modules_list(self, event: AstrMessageEvent):
        await self._require_group_admin(event)
        rows = await list_modules(self.context, event.unified_msg_origin)
        lines = ["Doge modules · 当前群", "默认全部开启；Legacy 不在此列表。"]
        for row in rows:
            state = "LOCK" if row.locked else ("ON" if row.enabled else "OFF")
            lines.append(f"  {state:<4} {row.short_name:<14} {row.description}")
        lines += ["", "/admin modules off <module>", "/admin modules on <module>", "/admin modules reset"]
        yield event.plain_result("\n".join(lines))

    @modules.command("on")
    async def modules_on(self, event: AstrMessageEvent, module: GreedyStr):
        await self._require_group_admin(event)
        row = await set_module_enabled(self.context, event.unified_msg_origin, str(module), True)
        yield event.plain_result(f"当前群已启用模块：{row.short_name}")

    @modules.command("off")
    async def modules_off(self, event: AstrMessageEvent, module: GreedyStr):
        await self._require_group_admin(event)
        row = await set_module_enabled(self.context, event.unified_msg_origin, str(module), False)
        yield event.plain_result(f"当前群已关闭模块：{row.short_name}\n对应指令和 Agent Tools 会同时在本群停用。")

    @modules.command("reset")
    async def modules_reset(self, event: AstrMessageEvent):
        await self._require_group_admin(event)
        await reset_modules(event.unified_msg_origin)
        yield event.plain_result("当前群模块已恢复默认：所有正式非 Legacy 模块开启。")

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
