"""Read-only, no-network, unprivileged KnotPy bridge for /math knot.

Dedicated short-lived sandbox prevents third-party knot-polynomial recursion
from exhausting AstrBot. Repo pinned to /opt/doge-science/knotpy b5fcf1a.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _calculate(source:str, poly:str="all"):
    source=source.strip()
    if source.lower().startswith("pd "):
        kind="pd"
        source=source[3:].strip().strip("\"\'")
    elif source.startswith(("[[","PD[")):
        kind="pd"
    else:
        kind="name"
    if poly not in {"all","alexander","jones","det"}:
        raise ValueError("poly 支持 all / alexander / jones / det")
    if kind=="name":
        if not re.fullmatch(r"(?:[+-]?[1-9][0-9]?_[1-9][0-9]{0,2}|unknot)",source):
            raise ValueError("结名示例：3_1 / 4_1 / 7_2；或 pd '[[1,5,2,4],...]'")
    else:
        if len(source)>750 or not re.fullmatch(r"[\d\s,\[\]XPD]+",source):
            raise ValueError("PD 需包含合法整数和 X[...] 结点，长度不可超过 750")
    worker=Path(__file__).with_name("math_knot_worker.py")
    if not worker.is_file():
        raise ValueError("结绳不变量计算后端缺少 worker 文件")
    bwrap=shutil.which("bwrap")
    if not bwrap:
        raise ValueError("缺少 bubblewrap 隔离器；为保证服务器安全，拒绝执行第三方计算")
    opts=[
        bwrap,"--unshare-user","--unshare-net","--die-with-parent",
        "--ro-bind","/usr","/usr",
        "--ro-bind","/lib","/lib",
        "--ro-bind","/lib64","/lib64",
        "--ro-bind","/root/.local/share/uv","/root/.local/share/uv",
        "--ro-bind","/opt/doge-science/knotpy","/knotpy",
        "--ro-bind",str(worker),"/worker.py",
        "--tmpfs","/tmp","--proc","/proc","--dev","/dev",
        "--uid","65534","--gid","65534",
        "--setenv","HOME","/tmp",
        "--setenv","PYTHONPATH","/knotpy",
        "--setenv","OPENBLAS_NUM_THREADS","1",
        "--setenv","MPLBACKEND","Agg",
        "--",
        sys.executable,"/worker.py",
    ]
    params={"source":source,"kind":kind,"poly":poly}
    try:
        process=subprocess.run(
            opts,input=json.dumps(params,ensure_ascii=False),text=True,
            capture_output=True,timeout=9,cwd="/",
            env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","LC_ALL":"C.UTF-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("结绳不变量计算超过 9 秒，已终止；请简化 PD 图") from exc
    data=None
    try:data=json.loads(process.stdout.strip()[-7000:])
    except (ValueError,TypeError):pass
    if process.returncode or not isinstance(data,dict):
        raise ValueError("结绳计算失败："+(str(data.get("error")) if isinstance(data,dict) else process.stderr[:120]))
    answer=[f"输入：{data['input']}",
            f"交叉数：{data['crossings']}",
            f"分支数：{data['components']}",
            f"后端：{data['library']}"]
    for label,key in (("Alexander Δ(t)","alexander"),("Jones V(t)","jones"),("行列式 |Δ(-1)|","determinant")):
        if key in data:answer.append(f"{label} = {data[key]}")
    answer.append("不变量来自真实平面结图，不能单凭同一个多项式证明两个结同痕或类型相同。")
    return "\n".join(answer)


_KNOT_LIMIT = asyncio.Semaphore(1)


async def knot_invariant(source:str, poly:str="all"):
    # Prevent multiple separate 420-MB knot workers competing with AstrBot.
    async with _KNOT_LIMIT:
        return await asyncio.to_thread(_calculate,source,poly)
