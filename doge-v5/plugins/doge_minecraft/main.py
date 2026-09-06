from __future__ import annotations

from datetime import datetime
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.presentation import text_result
from data.plugins.doge_shared.raw_command import command_payload

from .service import (add_server, cleanup_servers, delete_server, find_server, get_server_status,
                      read_json, render_server_info, update_server, update_server_status, validate_host)

HELP = """Doge Minecraft /mc
  /mc                         查询当前会话保存的全部 Java 服务器并渲染状态卡
  /mc add <名称> <地址> [force]   添加；默认先真实查询，force 可保存暂时离线服务器
  /mc get <名称|ID>           查看保存地址
  /mc del <名称|ID>           删除
  /mc up <名称|ID> <新名称|-> [新地址] [force]  更新；- 表示名称不变
  /mc list                    列出保存的服务器与 ID
  /mc cleanup                 删除连续 10 天没有成功查询的记录
  /mc help                    帮助
兼容 v4 子动作拼法：mcadd/mcget/mcdel/mcup/mclist/mccleanup。状态协议继续使用 v4 的 mcstatus 路线。"""


@register("doge_minecraft", "runnel", "v4 Minecraft Java 服务器状态查询、管理与卡片", "1.0.0")
class DogeMinecraft(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.default_icon = Path(__file__).resolve().parent / "resource" / "default_icon.png"

    @staticmethod
    def _scope(event: AstrMessageEvent) -> str:
        gid = str(event.get_group_id() or "").strip()
        if gid: return "group_" + gid
        return "private_" + str(event.get_sender_id() or "unknown")

    def _path(self, event: AstrMessageEvent) -> Path:
        root=Path(StarTools.get_data_dir("doge_minecraft")); root.mkdir(parents=True,exist_ok=True)
        return root / (self._scope(event) + ".json")

    async def _query_all(self, event: AstrMessageEvent):
        path=self._path(event)
        data=await read_json(path); servers=data.get("servers",{})
        if not servers:
            yield text_result(event,"还没有保存服务器。用 /mc add <名称> <地址> 添加。",markdown=False); return
        chain=[]
        # v4 queried only after cleanup, so an online server could be deleted merely
        # because nobody asked for it for 10 days. Probe first, refresh successes,
        # then remove only records that are still stale after this real attempt.
        for sid,item in servers.items():
            status=await get_server_status(str(item["host"]))
            await update_server_status(path,str(sid),bool(status))
            if not status: continue
            png=render_server_info(status,server_name=f"[{sid}] {item['name']}",default_icon=self.default_icon)
            chain.append(Comp.Image.fromBytes(png))
        deleted=await cleanup_servers(path)
        if deleted:
            names="、".join(str(x.get("name")) for x in deleted)
            yield text_result(event,f"已清理在本次查询后仍连续 10 天未成功的服务器：{names}",markdown=False)
        if not chain:
            remaining=(await read_json(path)).get("servers",{})
            msg="保存的服务器当前都无法查询；失败状态已记录。" if remaining else "保存的服务器当前都无法查询，且过期记录已清理。"
            yield text_result(event,msg,markdown=False); return
        result=event.chain_result(chain); result.use_markdown(False); yield result

    async def _dispatch(self,event: AstrMessageEvent,payload:str):
        raw=payload.strip()
        if not raw:
            async for x in self._query_all(event): yield x
            return
        parts=raw.split(); action=parts[0].casefold(); args=parts[1:]
        aliases={"mcadd":"add","mcget":"get","mcdel":"del","mcup":"up","mclist":"list","mccleanup":"cleanup","mchelp":"help"}
        action=aliases.get(action,action)
        path=self._path(event)
        if action in {"help","?"}:
            yield text_result(event,HELP,markdown=False); return
        if action == "list":
            data=await read_json(path); servers=data.get("servers",{})
            if not servers: yield text_result(event,"没有保存的服务器",markdown=False); return
            lines=["当前保存的 Minecraft 服务器："]+[f"{sid}. {x['name']} — {x['host']}" for sid,x in servers.items()]
            yield text_result(event,"\n".join(lines),markdown=False); return
        if action == "get":
            if len(args)!=1: raise ValueError("用法：/mc get <名称|ID>")
            found=find_server(await read_json(path),args[0])
            if not found: raise ValueError(f"没有找到服务器 {args[0]}")
            sid,item=found; yield text_result(event,f"{item['name']} (ID: {sid})\n{item['host']}",markdown=False); return
        if action == "add":
            if len(args)<2 or len(args)>3: raise ValueError("用法：/mc add <名称> <地址> [force]")
            name,host=args[0],validate_host(args[1]); force=len(args)==3 and args[2].casefold() in {"force","true","1","yes"}
            status=None if force else await get_server_status(host)
            if not force and status is None: raise ValueError("预查询失败；确认地址后可在末尾加 force 强制保存")
            ok,sid=await add_server(path,name,host,initial_success=status is not None)
            if not ok: raise ValueError("同名服务器或相同地址已经存在")
            yield text_result(event,f"成功添加服务器 {name} (ID: {sid})",markdown=False); return
        if action in {"del","delete","rm"}:
            if len(args)!=1: raise ValueError("用法：/mc del <名称|ID>")
            if not await delete_server(path,args[0]): raise ValueError(f"没有找到服务器 {args[0]}")
            yield text_result(event,f"成功删除服务器 {args[0]}",markdown=False); return
        if action in {"up","update"}:
            if len(args)<2 or len(args)>4: raise ValueError("用法：/mc up <名称|ID> <新名称|-> [新地址] [force]")
            ident=args[0]; new_name=None if args[1]=='-' else args[1]; new_host=None; force=False
            before=find_server(await read_json(path),ident)
            if not before: raise ValueError(f"没有找到服务器 {ident}")
            stable_id=before[0]
            if len(args)>=3 and args[2].casefold() not in {"force","true","1","yes"}: new_host=validate_host(args[2])
            if args[-1].casefold() in {"force","true","1","yes"}: force=True
            preflight=None
            if new_host and not force:
                preflight=await get_server_status(new_host)
                if preflight is None: raise ValueError("新地址预查询失败；确认后可在末尾加 force")
            if not await update_server(path,ident,new_name=new_name,new_host=new_host): raise ValueError("服务器不存在，或新名称/地址与现有记录冲突")
            if preflight is not None:
                await update_server_status(path,stable_id,True)
            found=find_server(await read_json(path),stable_id)
            sid,item=found if found else (ident,{"name":new_name or ident})
            yield text_result(event,f"成功更新服务器 {item['name']} (ID: {sid})",markdown=False); return
        if action == "cleanup":
            deleted=await cleanup_servers(path)
            if not deleted: yield text_result(event,"没有需要清理的服务器",markdown=False); return
            lines=["已清理以下 10 天未成功查询的服务器："]
            for x in deleted:
                anchor=x.get('last_success_time') or x.get('created_time')
                when=datetime.fromtimestamp(int(anchor)).strftime('%Y-%m-%d %H:%M:%S') if anchor else '未知'
                lines.append(f"• {x['name']} (ID: {x['id']}) — {x['host']} — 最近成功/建立: {when}")
            yield text_result(event,"\n".join(lines),markdown=False); return
        raise ValueError("未知子命令。用 /mc help 查看。")

    @filter.command("mc")
    async def mc(self,event: AstrMessageEvent):
        try:
            payload=command_payload(event.message_str,"mc")
            async for x in self._dispatch(event,payload): yield x
        except Exception as exc:
            logger.warning("doge minecraft failed: %s: %s",type(exc).__name__,exc)
            yield text_result(event,format_cli_error("mc",exc),markdown=False)
