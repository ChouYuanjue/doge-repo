"""Automatic *local* LaTeX -> image rendering at the outgoing LLM boundary.

The official QQ adapter and OneBot do not consistently display LaTeX.  Parse
only explicit math spans or high-confidence bare macros outside code blocks,
preserve text/media order and never send model output to a third-party TeX
service.  Reuses existing Typst + cmarker/MiTeX instead of a new TeX engine.
"""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import astrbot.api.message_components as Comp

from .markdown_typeset import render_markdown
from .presentation import markdown_to_plain
from .typeset import render_tex

# Code fences and inline backticks always take priority over math delimiters.
_CODE = re.compile(
    r"(?ms)^[ \t]*(?P<fence>[\x60]{3,}|~{3,})[^\n]*\n.*?^[ \t]*(?P=fence)[ \t]*(?:\n|$)|"
    r"(?<!\x60)\x60(?!\x60)[^\n\x60]*\x60",
)
_ENV = r"(?:aligned|align\*?|equation\*?|gather\*?|multline\*?|matrix|pmatrix|bmatrix|vmatrix|cases|split)"
_MATH = re.compile(
    r"(?<!\\)\$\$(?P<display>.{1,2500}?)(?<!\\)\$\$|"
    r"\\\[(?P<bracket>.{1,2500}?)\\\]|"
    r"\\\((?P<round>.{1,2000}?)\\\)|"
    r"\\begin\{(?P<env>"+_ENV+r")\}(?P<environment>.{1,2300}?)\\end\{(?P=env)\}|"
    r"(?<![\\$])\$(?!\$)(?P<inline>[^\n$]{1,1000}?)(?<!\\)\$(?!\$)",
    re.DOTALL,
)
_BARE_MACRO = re.compile(
    r"\\(?:frac|dfrac|tfrac)\s*\{(?:[^{}]|\{[^{}]*\}){1,100}\}\s*\{(?:[^{}]|\{[^{}]*\}){1,100}\}|"
    r"\\(?:sqrt|boxed|overline|underline|vec|hat|bar)\s*\{(?:[^{}]|\{[^{}]*\}){1,160}\}",
)
_BAD_MATH = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SINGLE_DOLLAR_CLUE = re.compile(r"[\\^_=]|\b[a-zA-Z]\b|[+\-*/<>∫∑√]")
_MAX_AUTO_FORMULAS = 4
_MAX_REPLY_LENGTH = 18000
_MAX_FORMULA_LENGTH = 1250


def _valid_tex(expr: str, *, single_dollar: bool = False) -> bool:
    expr=expr.strip()
    if not 1 <= len(expr) <= _MAX_FORMULA_LENGTH or _BAD_MATH.search(expr):
        return False
    if single_dollar:
        # "$10 and $20" is ordinary money, not a TeX fragment. Require a
        # formula symbol and reject purely numeric or prose-like price ranges.
        if not _SINGLE_DOLLAR_CLUE.search(expr):
            return False
        if (re.fullmatch(r"[\d\s.,+\-]+",expr) or
            re.fullmatch(r"[\d\s.,]+\s+(?:and|to|or|至|到)\s*",expr,re.I)):
            return False
    return True


def _bare_math_segments(text: str):
    """Conservatively detect macros that occur without explicit math delimiters."""
    cursor=0
    for match in _BARE_MACRO.finditer(text):
        if match.start()>cursor:
            yield ("text",text[cursor:match.start()],None)
        yield ("math",match.group(0),match.group(0))
        cursor=match.end()
    if cursor<len(text):
        yield ("text",text[cursor:],None)


def _plain_math_segments(text: str):
    cursor=0
    for match in _MATH.finditer(text):
        kind=match.lastgroup
        expr=(match.group(kind) or "") if kind else ""
        if kind=="environment":
            expr=match.group(0)
        if not _valid_tex(expr,single_dollar=(kind=="inline")):
            continue
        if match.start()>cursor:
            yield from _bare_math_segments(text[cursor:match.start()])
        yield ("math",expr.strip(),match.group(0))
        cursor=match.end()
    if cursor<len(text):
        yield from _bare_math_segments(text[cursor:])


def split_latex_reply(text: str) -> list[tuple[str,str,str|None]]:
    """Split text/math while keeping math inside code fences as literal text."""
    source=str(text or "")
    if not source:
        return []
    result=[]
    cursor=0
    for match in _CODE.finditer(source):
        if cursor<match.start():
            result.extend(_plain_math_segments(source[cursor:match.start()]))
        result.append(("text",match.group(0),None))
        cursor=match.end()
    if cursor<len(source):
        result.extend(_plain_math_segments(source[cursor:]))
    # Explicitly ensure a full plain message without any formula is retained.
    return result or [("text",source,None)]


def has_latex_reply(text: str) -> bool:
    return len(text)<=_MAX_REPLY_LENGTH and any(kind=="math" for kind,_,_ in split_latex_reply(text))


def _plain_text(src: str, *, onebot: bool, markdown: bool) -> str:
    if not (onebot or not markdown):
        return src
    if not src:
        return ""
    # markdown_to_plain() strips edges; preserve meaningful whitespace
    # between text and adjacent formula image segments.
    leading=re.match(r"^\s*",src).group(0)
    trailing=re.search(r"\s*$",src).group(0)
    middle=markdown_to_plain(src)
    if not middle:
        return src if src.isspace() else ""
    return leading+middle+trailing


async def _render_one(root: Path, expression: str) -> Path:
    payload="$$\n"+expression+"\n$$"
    try:
        paths,_=await asyncio.wait_for(
            asyncio.to_thread(render_markdown,root,payload,"card",165.0),
            timeout=8.0,
        )
        if len(paths)==1 and paths[0].stat().st_size>200:
            return paths[0]
    except Exception:
        pass
    # Only local MathText as a fallback; never send unsolicited user/model
    # content to an external formula rendering website.
    path,_=await asyncio.wait_for(render_tex(root,expression,"local"),timeout=6.0)
    return path


class AutoMathRenderer:
    def __init__(self, root:Path):
        self.root=Path(root)/"auto-tex"
        self._lock=asyncio.Semaphore(1)
        self._last_cleanup=0.

    def _sweep_old(self):
        now=time.time()
        if now-self._last_cleanup<600:
            return
        self._last_cleanup=now
        try:
            for file in list(self.root.rglob("markdown-*.png"))[:120]:
                if now-file.stat().st_mtime>24*3600:
                    file.unlink(missing_ok=True)
            for file in list(self.root.rglob("tex-*.png"))[:120]:
                if now-file.stat().st_mtime>24*3600:
                    file.unlink(missing_ok=True)
        except OSError:
            pass

    async def render_chain(self, chain, *, onebot:bool, markdown:bool):
        """Return (new_chain, any_images), preserving all non-Plain results."""
        if not chain or not all(isinstance(c,Comp.Plain) for c in chain):
            return chain,False
        source="\n".join(str(c.text or "") for c in chain)
        if len(source)>_MAX_REPLY_LENGTH:
            return [Comp.Plain(_plain_text(source,onebot=onebot,markdown=markdown))],False
        spans=split_latex_reply(source)
        if not any(kind=="math" for kind,_,_ in spans):
            return [Comp.Plain(_plain_text(source,onebot=onebot,markdown=markdown))],False
        self.root.mkdir(parents=True,exist_ok=True)
        self._sweep_old()
        output=[]
        rendered=0
        for kind,payload,original in spans:
            if kind=="text":
                s=_plain_text(payload,onebot=onebot,markdown=False)
                if s:output.append(Comp.Plain(s))
                continue
            if rendered>=_MAX_AUTO_FORMULAS:
                output.append(Comp.Plain(original or payload))
                continue
            try:
                async with self._lock:
                    p=await _render_one(self.root,payload)
                output.append(Comp.Image.fromFileSystem(str(p)))
                rendered+=1
            except Exception:
                # Rendering is best-effort; preserve formula source faithfully.
                output.append(Comp.Plain(original or payload))
        return output or chain,rendered>0
