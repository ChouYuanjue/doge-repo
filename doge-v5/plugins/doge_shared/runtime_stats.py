from __future__ import annotations

import ast
import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from threading import Lock

_EVENT_RE = re.compile(r"\[core\.event_bus:74\]:\s+\[[^]]+\]\s+\[([^]]+)\].*?:\s(.*)$")


def _fmt_bytes(n: int) -> str:
    x = float(max(0, n))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if x < 1024 or unit == "TiB":
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024
    return f"{x:.1f} TiB"


def _fmt_duration(seconds: float) -> str:
    sec = max(0, int(seconds))
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, _ = divmod(sec, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _read_meminfo() -> tuple[int, int]:
    vals: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, raw = line.split(":", 1)
            vals[key] = int(raw.strip().split()[0]) * 1024
    except Exception:
        return 0, 0
    total = vals.get("MemTotal", 0)
    avail = vals.get("MemAvailable", 0)
    return total, max(0, total - avail)


def _read_uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        return 0.0


def _process_rss() -> int:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


def git_revision(repo_root: Path) -> str:
    try:
        cp = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        if cp.returncode == 0:
            return cp.stdout.strip()
    except Exception:
        pass
    return "unknown"


def version_snapshot(repo_root: Path) -> dict[str, str]:
    try:
        import importlib.metadata as md
        astrbot_ver = md.version("astrbot")
    except Exception:
        astrbot_ver = "unknown"
    return {
        "doge": "5.5.0",
        "git": git_revision(repo_root),
        "astrbot": astrbot_ver,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
    }


def system_snapshot(data_root: Path) -> dict[str, object]:
    mem_total, mem_used = _read_meminfo()
    disk = shutil.disk_usage(str(data_root))
    try:
        load1, load5, load15 = os.getloadavg()
    except OSError:
        load1 = load5 = load15 = 0.0
    return {
        "host_uptime": _fmt_duration(_read_uptime()),
        "load": f"{load1:.2f} / {load5:.2f} / {load15:.2f}",
        "memory": f"{_fmt_bytes(mem_used)} / {_fmt_bytes(mem_total)}",
        "memory_pct": (100.0 * mem_used / mem_total) if mem_total else 0.0,
        "disk": f"{_fmt_bytes(disk.used)} / {_fmt_bytes(disk.total)}",
        "disk_pct": (100.0 * disk.used / disk.total) if disk.total else 0.0,
        "astrbot_rss": _fmt_bytes(_process_rss()),
        "ports": {6099: _port_open(6099), 6185: _port_open(6185), 6199: _port_open(6199)},
    }


def _extract_command(message: str) -> str | None:
    text = (message or "").strip()
    if not text.startswith("/"):
        return None
    bits = text[1:].split()
    if not bits:
        return None
    head = bits[0].lower()
    if head == "admin" and len(bits) > 1:
        return "admin " + bits[1].lower()
    return head


class UsageCounter:
    """Tiny persistent aggregate counter. No message bodies or user identifiers are stored."""

    def __init__(self, path: Path, log_dir: Path):
        self.path = Path(path)
        self.log_dir = Path(log_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.data = self._load_or_bootstrap()

    @staticmethod
    def _blank() -> dict:
        return {
            "schema": 1,
            "started_at": int(time.time()),
            "messages": 0,
            "commands": 0,
            "by_platform": {},
            "by_command": {},
            "by_date": {},
        }

    def _load_or_bootstrap(self) -> dict:
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                if d.get("schema") == 1:
                    return d
            except Exception:
                pass
        d = self._blank()
        for log in sorted(self.log_dir.glob("astrbot.log*")):
            try:
                lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line in lines:
                m = _EVENT_RE.search(line)
                if not m:
                    continue
                platform_name, msg = m.groups()
                d["messages"] += 1
                d["by_platform"][platform_name] = d["by_platform"].get(platform_name, 0) + 1
                cmd = _extract_command(msg)
                if cmd:
                    d["commands"] += 1
                    d["by_command"][cmd] = d["by_command"].get(cmd, 0) + 1
        self._save(d)
        return d

    def _save(self, data: dict | None = None) -> None:
        payload = data if data is not None else self.data
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    def record(self, platform_name: str, message: str) -> None:
        day = time.strftime("%Y-%m-%d", time.localtime())
        cmd = _extract_command(message)
        with self._lock:
            self.data["messages"] += 1
            p = platform_name or "unknown"
            self.data["by_platform"][p] = self.data["by_platform"].get(p, 0) + 1
            self.data["by_date"][day] = self.data["by_date"].get(day, 0) + 1
            if cmd:
                self.data["commands"] += 1
                self.data["by_command"][cmd] = self.data["by_command"].get(cmd, 0) + 1
            self._save()

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self.data))


def product_counts(v5_root: Path) -> dict[str, int]:
    manifest = json.loads((v5_root / "plugin_manifest.json").read_text(encoding="utf-8"))
    defaults = [x["name"] for x in manifest["plugins"] if x.get("default") and x.get("status") not in {"planned", "merged"}]
    commands: set[str] = set()
    for name in defaults:
        p = v5_root / "plugins" / name / "main.py"
        if not p.exists():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                if deco.func.attr not in {"command", "command_group"}:
                    continue
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    commands.add(str(deco.args[0].value))
    return {"plugins": len(defaults), "commands": len(commands)}


def provider_aggregates(db_path: Path) -> dict[str, int | float]:
    out: dict[str, int | float] = {"requests": 0, "tokens": 0, "output_tokens": 0, "avg_latency": 0.0}
    if not db_path.exists():
        return out
    try:
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.5)
        row = c.execute(
            "select count(*), coalesce(sum(token_input_other+token_input_cached+token_output),0), "
            "coalesce(sum(token_output),0), coalesce(avg(end_time-start_time),0) from provider_stats"
        ).fetchone()
        if row:
            out = {"requests": int(row[0]), "tokens": int(row[1]), "output_tokens": int(row[2]), "avg_latency": float(row[3])}
        c.close()
    except Exception:
        pass
    return out


def top_counts(mapping: dict[str, int], n: int = 5) -> list[tuple[str, int]]:
    return Counter(mapping).most_common(n)
