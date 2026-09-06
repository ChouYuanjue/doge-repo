from __future__ import annotations

import asyncio
import base64
import copy
import io
import ipaddress
import json
import os
import re
import socket
import time
from pathlib import Path
from typing import Any

import aiohttp
from astrbot.api import logger
from mcstatus import JavaServer
from PIL import Image, ImageDraw, ImageFont

CURRENT_VERSION = "2.2"
AUTO_CLEANUP_DAYS = 10
CSU_HOST = "csu-mc.org"
CSU_PLAYERS_URL = "https://map.magicalsheep.cn/tiles/players.json"
DEFAULT_CONFIG = {"version": CURRENT_VERSION, "next_id": 1, "servers": {}, "last_cleanup": None}
_HOST_RE = re.compile(r"^[A-Za-z0-9._:\-\[\]]+$")
_LOCKS: dict[str, asyncio.Lock] = {}


def fresh_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def validate_host(host: str) -> str:
    value = str(host or "").strip()
    if not value or len(value) > 300 or not _HOST_RE.fullmatch(value):
        raise ValueError("服务器地址格式不正确，只能包含主机名/IP、端口以及 .:-[]")
    return value


def _normalize_server(item: dict[str, Any], sid: str, now: int) -> bool:
    changed = False
    defaults = {
        "id": int(sid) if str(sid).isdigit() else sid,
        "created_time": now,
        "last_success_time": None,
        "last_failed_time": None,
        "failed_count": 0,
    }
    for key, value in defaults.items():
        if key not in item:
            item[key] = value
            changed = True
    return changed


def migrate_old_format(data: dict[str, Any], *, now: int | None = None) -> dict[str, Any]:
    """Migrate v4 name-keyed files without making them immediately cleanup-eligible."""
    if not data or "version" in data:
        return data
    now = int(now or time.time())
    new = fresh_config()
    next_id = 1
    for name, old in data.items():
        if not isinstance(old, dict) or "host" not in old:
            continue
        sid = str(next_id)
        new["servers"][sid] = {
            "id": next_id,
            "name": str(old.get("name") or name),
            "host": str(old["host"]),
            "created_time": now,
            "last_success_time": None,
            "last_failed_time": None,
            "failed_count": 0,
        }
        next_id += 1
    new["next_id"] = next_id
    return new


def _read_sync(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return fresh_config(), True
    data = json.loads(path.read_text(encoding="utf-8"))
    migrated = "version" not in data
    data = migrate_old_format(data)
    changed = migrated
    if not isinstance(data.get("servers"), dict):
        data["servers"] = {}; changed = True
    if not isinstance(data.get("next_id"), int):
        ids = [int(x) for x in data["servers"] if str(x).isdigit()]
        data["next_id"] = max(ids, default=0) + 1; changed = True
    if data.get("version") != CURRENT_VERSION:
        data["version"] = CURRENT_VERSION; changed = True
    data.setdefault("last_cleanup", None)
    now = int(time.time())
    for sid, item in list(data["servers"].items()):
        if not isinstance(item, dict) or not item.get("name") or not item.get("host"):
            continue
        changed = _normalize_server(item, str(sid), now) or changed
    return data, changed


def _write_sync(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _lock(path: Path) -> asyncio.Lock:
    return _LOCKS.setdefault(str(path.resolve()), asyncio.Lock())


async def read_json(path: Path) -> dict[str, Any]:
    async with _lock(path):
        data, changed = await asyncio.to_thread(_read_sync, path)
        if changed:
            await asyncio.to_thread(_write_sync, path, data)
        return copy.deepcopy(data)


async def _mutate(path: Path, fn):
    async with _lock(path):
        data, _ = await asyncio.to_thread(_read_sync, path)
        result = fn(data)
        await asyncio.to_thread(_write_sync, path, data)
        return result


def find_server(data: dict[str, Any], identifier: str) -> tuple[str, dict[str, Any]] | None:
    servers = data.get("servers", {})
    ident = str(identifier)
    if ident in servers:
        return ident, servers[ident]
    for sid, item in servers.items():
        if str(item.get("name")) == ident:
            return str(sid), item
    return None


async def add_server(path: Path, name: str, host: str, *, initial_success: bool) -> tuple[bool, str | None]:
    host = validate_host(host); name = str(name or "").strip()
    if not name:
        raise ValueError("服务器名称不能为空")
    def op(data):
        servers = data["servers"]
        if any(str(x.get("name")) == name or str(x.get("host")) == host for x in servers.values()):
            return False, None
        sid = str(data["next_id"]); data["next_id"] += 1; now = int(time.time())
        servers[sid] = {"id": int(sid), "name": name, "host": host, "created_time": now,
                        "last_success_time": now if initial_success else None,
                        "last_failed_time": None, "failed_count": 0}
        return True, sid
    return await _mutate(path, op)


async def delete_server(path: Path, identifier: str) -> bool:
    def op(data):
        found = find_server(data, identifier)
        if not found: return False
        del data["servers"][found[0]]; return True
    return await _mutate(path, op)


async def update_server(path: Path, identifier: str, *, new_name: str | None = None, new_host: str | None = None) -> bool:
    if new_host is not None: new_host = validate_host(new_host)
    def op(data):
        found = find_server(data, identifier)
        if not found: return False
        sid, item = found
        if new_name is not None:
            n = new_name.strip()
            if not n: return False
            if any(k != sid and str(v.get("name")) == n for k,v in data["servers"].items()): return False
            item["name"] = n
        if new_host is not None:
            if any(k != sid and str(v.get("host")) == new_host for k,v in data["servers"].items()): return False
            item["host"] = new_host
        return True
    return await _mutate(path, op)


async def update_server_status(path: Path, identifier: str, success: bool) -> bool:
    def op(data):
        found = find_server(data, identifier)
        if not found: return False
        _, item = found; now = int(time.time())
        if success:
            item["last_success_time"] = now; item["failed_count"] = 0
        else:
            item["last_failed_time"] = now; item["failed_count"] = int(item.get("failed_count") or 0) + 1
        return True
    return await _mutate(path, op)


async def cleanup_servers(path: Path, *, now: int | None = None) -> list[dict[str, Any]]:
    now = int(now or time.time()); cutoff = now - AUTO_CLEANUP_DAYS * 86400
    def op(data):
        deleted=[]
        for sid,item in list(data["servers"].items()):
            # v4 migration bug fixed: unknown historical success uses migration/creation time,
            # not Unix epoch, so migrating a valid old file never deletes it immediately.
            anchor = item.get("last_success_time") or item.get("created_time") or now
            if int(anchor) < cutoff:
                deleted.append({"id": sid, **copy.deepcopy(item)})
                del data["servers"][sid]
        data["last_cleanup"] = now
        return deleted
    return await _mutate(path, op)


async def fetch_csu_players() -> list[str]:
    timeout=aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(CSU_PLAYERS_URL) as response:
            response.raise_for_status(); data=await response.json(content_type=None)
    return sorted(str(x.get("name")) for x in data.get("players", []) if x.get("name") and not str(x.get("name")).startswith("bot_"))


async def get_server_status(host: str, *, timeout: float = 7.0) -> dict[str, Any] | None:
    host = validate_host(host)
    try:
        server = await JavaServer.async_lookup(host, timeout=min(3.0, timeout))
        status = await asyncio.wait_for(server.async_status(tries=1), timeout=timeout)
        players = sorted(p.name for p in (status.players.sample or []) if getattr(p, "name", None))
        base_host = host
        if host.startswith("["):
            base_host = host[1:].split("]",1)[0]
        elif host.count(":") <= 1:
            base_host = host.rsplit(":",1)[0] if ":" in host else host
        if base_host.casefold() == CSU_HOST:
            try: players = await fetch_csu_players()
            except Exception as exc: logger.warning("CSU player-map fallback failed: %s", type(exc).__name__)
        return {"players_list": players, "latency": int(status.latency), "plays_max": int(status.players.max),
                "plays_online": int(status.players.online), "server_version": str(status.version.name),
                "icon_base64": status.icon or ""}
    except (socket.gaierror, ConnectionRefusedError, asyncio.TimeoutError, OSError) as exc:
        logger.info("Minecraft server unavailable %s: %s", host, type(exc).__name__)
        return None
    except Exception as exc:
        logger.warning("Minecraft status failed %s: %s: %s", host, type(exc).__name__, exc)
        return None


def _font(size: int, *, bold: bool=False):
    candidates = [
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-droid/DroidSansFallback.ttf",
        str(Path(__file__).resolve().parents[3] / "doge-v4" / "mc" / "resource" / "msyh.ttf"),
    ]
    for p in candidates:
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()


def _decode_icon(icon_base64: str | None, default_icon: Path | None) -> Image.Image | None:
    try:
        if icon_base64:
            raw = str(icon_base64).split(",",1)[-1]
            return Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGBA")
        if default_icon and default_icon.exists():
            return Image.open(default_icon).convert("RGBA")
    except Exception:
        return None
    return None


def render_server_info(status: dict[str, Any], *, server_name: str, default_icon: Path | None=None) -> bytes:
    """v4 card layout, fixed to use real synchronous font objects and return PNG bytes."""
    icon=_decode_icon(status.get("icon_base64"),default_icon)
    title_font=_font(30,bold=True); text_font=_font(20); small_font=_font(18)
    players=[str(x) for x in status.get("players_list") or []]
    chunks=[players[i:i+4] for i in range(0,len(players),4)] or [[]]
    h=190 + len(chunks)*32
    img=Image.new("RGB",(600,h),(34,34,34)); draw=ImageDraw.Draw(img)
    base_y=20; icon_size=64 if icon else 0; text_x=20+icon_size+20
    if icon:
        icon.thumbnail((64,64)); mask=Image.new("L",(64,64),0); md=ImageDraw.Draw(mask); md.rounded_rectangle((0,0,63,63),radius=10,fill=255)
        canvas=Image.new("RGBA",(64,64),(0,0,0,0)); canvas.paste(icon,(0,0)); img.paste(canvas,(20,base_y),mask)
    draw.text((text_x,base_y),server_name,font=title_font,fill=(85,255,85)); base_y += 40
    latency=int(status.get("latency") or 0); lc=(85,255,85) if latency<100 else (255,170,0) if latency<200 else (255,85,85)
    draw.text((text_x,base_y),f"版本: {status.get('server_version') or '未知'}",font=text_font,fill=(255,255,255))
    draw.text((420,base_y),f"延迟: {latency}ms",font=text_font,fill=lc); base_y += 40
    draw.text((text_x,base_y),f"在线玩家 ({int(status.get('plays_online') or 0)}/{int(status.get('plays_max') or 0)})",font=text_font,fill=(85,255,85)); base_y += 40
    if players:
        for chunk in chunks:
            draw.text((text_x+10,base_y)," • ".join(chunk),font=small_font,fill=(255,255,255)); base_y += 30
    else:
        draw.text((text_x+10,base_y),"暂无玩家在线",font=small_font,fill=(255,255,255))
    draw.rounded_rectangle([10,10,img.width-10,img.height-10],radius=10,outline=(85,255,85),width=2)
    out=io.BytesIO(); img.save(out,format="PNG"); return out.getvalue()
