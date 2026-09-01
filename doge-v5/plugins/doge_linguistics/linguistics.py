from __future__ import annotations

import asyncio
import json
import math
import re
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import aiohttp


_CJK_RE = re.compile(r"[\u3400-\u9fff\U00020000-\U000323af]")
_PUNCT_RE = re.compile(r"[，。！？；：、,.;:!?/|]+")
_PARENS_RE = re.compile(r"[（(【\[].*?[）)】\]]")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "").strip().lower())


def _cn_terms(text: str) -> tuple[str, ...]:
    raw = unicodedata.normalize("NFKC", text or "").strip()
    if not raw:
        return ()
    # Parenthetical notes such as “（人名）” are metadata, not the lexical gloss.
    without_notes = _PARENS_RE.sub("", raw)
    pieces = [without_notes, *_PUNCT_RE.split(without_notes)]
    out: list[str] = []
    for piece in pieces:
        term = _norm(piece.strip("《》〈〉“”‘’ \t\n"))
        if term and term not in out:
            out.append(term)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class TangutEntry:
    key: str
    gx: str
    ghc: str
    en: str
    cn: str
    kind: str

    @classmethod
    def from_json(cls, obj: dict) -> "TangutEntry":
        if "word" in obj:
            key, kind = str(obj.get("word") or ""), "word"
        else:
            key, kind = str(obj.get("character") or ""), "character"
        return cls(
            key=key,
            gx=str(obj.get("GX") or ""),
            ghc=str(obj.get("GHC") or ""),
            en=str(obj.get("explanationEN") or ""),
            cn=str(obj.get("explanationCN") or ""),
            kind=kind,
        )

    def one_line(self) -> str:
        pron = " · ".join(x for x in (self.gx and f"GX {self.gx}", self.ghc and f"GHC {self.ghc}") if x)
        gloss = " / ".join(x for x in (self.cn, self.en) if x)
        return f"{self.key} — {gloss}" + (f" 〔{pron}〕" if pron else "")


@dataclass(frozen=True, slots=True)
class TangutUnit:
    source: str
    entry: TangutEntry | None


@dataclass(frozen=True, slots=True)
class ZhSegment:
    source: str
    chosen: TangutEntry | None
    alternatives: tuple[TangutEntry, ...] = ()


class TangutDictionary:
    """A conservative, dictionary-grounded Tangut lookup/translation layer.

    The v4 code used jieba plus exact reverse keywords and then picked the
    shortest returned glyph. This implementation separates lookup from
    translation, uses exact/substring/coverage ranking for lookup, and uses a
    dynamic-programming exact-gloss segmentation for Chinese->Tangut so fuzzy
    matches never silently become translation output.
    """

    def __init__(self, path: Path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.entries = [TangutEntry.from_json(x) for x in payload]
        self.entries = [x for x in self.entries if x.key]
        self.forward: dict[str, TangutEntry] = {x.key: x for x in self.entries}
        self.cn_exact: dict[str, list[TangutEntry]] = defaultdict(list)
        self.en_exact: dict[str, list[TangutEntry]] = defaultdict(list)
        self.cn_char_index: dict[str, set[int]] = defaultdict(set)
        self.cn_df: dict[str, int] = defaultdict(int)
        self._entry_id = {id(entry): idx for idx, entry in enumerate(self.entries)}

        for idx, entry in enumerate(self.entries):
            terms = _cn_terms(entry.cn)
            seen_chars: set[str] = set()
            for term in terms:
                self.cn_exact[term].append(entry)
                for ch in term:
                    if _CJK_RE.match(ch):
                        self.cn_char_index[ch].add(idx)
                        seen_chars.add(ch)
            for ch in seen_chars:
                self.cn_df[ch] += 1
            for term in re.split(r"[\s.,;/]+", entry.en.lower()):
                term = _norm(term)
                if term:
                    self.en_exact[term].append(entry)
        self.key_lengths = sorted({len(k) for k in self.forward}, reverse=True)
        self.max_cn_term = min(8, max((len(k) for k in self.cn_exact), default=1))

    def by_tangut(self, text: str) -> list[TangutEntry]:
        q = text.strip()
        if q in self.forward:
            return [self.forward[q]]
        return [entry for key, entry in self.forward.items() if q and q in key][:20]

    def _idf(self, ch: str) -> float:
        return math.log((len(self.entries) + 1) / (self.cn_df.get(ch, 0) + 1)) + 1.0

    def search_chinese(self, query: str, limit: int = 10) -> list[tuple[TangutEntry, float]]:
        q = _norm(query)
        if not q:
            return []
        exact = self.cn_exact.get(q, [])
        candidate_ids: set[int] = {self._entry_id[id(x)] for x in exact}
        qchars = [ch for ch in q if _CJK_RE.match(ch)]
        char_sets = [self.cn_char_index.get(ch, set()) for ch in set(qchars)]
        if char_sets:
            intersection = set.intersection(*char_sets) if all(char_sets) else set()
            if intersection:
                candidate_ids.update(intersection)
            else:
                for s in char_sets:
                    candidate_ids.update(s)
        if not candidate_ids:
            return []

        q_bigrams = {q[i : i + 2] for i in range(max(0, len(q) - 1))}
        denom = sum(self._idf(ch) for ch in set(qchars)) or 1.0
        scored: list[tuple[TangutEntry, float]] = []
        for idx in candidate_ids:
            entry = self.entries[idx]
            cn = _norm(entry.cn)
            terms = _cn_terms(entry.cn)
            score = 0.0
            if cn == q:
                score += 120.0
            if q in terms:
                score += 100.0
            if q in cn:
                score += 30.0 + min(20.0, len(q) * 3.0)
            coverage = sum(self._idf(ch) for ch in set(qchars) if ch in cn) / denom
            score += coverage * 24.0
            if q_bigrams:
                matched = sum(1 for bg in q_bigrams if bg in cn)
                score += 18.0 * matched / len(q_bigrams)
            score -= max(0, len(cn) - len(q)) * 0.18
            if len(q) > 1 and entry.kind == "word":
                score += 2.0
            scored.append((entry, score))
        scored.sort(key=lambda x: (-x[1], len(x[0].key), x[0].key))
        return scored[: max(1, min(limit, 30))]

    def search_english(self, query: str, limit: int = 10) -> list[TangutEntry]:
        q = _norm(query)
        if not q:
            return []
        exact = list(self.en_exact.get(q, []))
        if len(exact) >= limit:
            return exact[:limit]
        seen = {x.key for x in exact}
        fuzzy = [x for x in self.entries if q in _norm(x.en) and x.key not in seen]
        fuzzy.sort(key=lambda x: (len(x.en), len(x.key)))
        return (exact + fuzzy)[:limit]

    def parse_tangut(self, text: str) -> list[TangutUnit]:
        text = text.strip()
        units: list[TangutUnit] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch.isspace() or unicodedata.category(ch).startswith("P"):
                units.append(TangutUnit(ch, None)); i += 1; continue
            found: TangutEntry | None = None
            source = ch
            for length in self.key_lengths:
                if i + length > len(text):
                    continue
                candidate = text[i : i + length]
                entry = self.forward.get(candidate)
                if entry is not None:
                    found, source = entry, candidate
                    break
            units.append(TangutUnit(source, found))
            i += len(source)
        return units

    def literal_gloss(self, text: str) -> tuple[list[TangutUnit], str]:
        units = self.parse_tangut(text)
        chunks: list[str] = []
        for unit in units:
            if unit.entry:
                chunks.append(unit.entry.cn or unit.entry.en or unit.source)
            else:
                chunks.append(unit.source)
        return units, " / ".join(x for x in chunks if x.strip())

    def pronunciation(self, text: str, system: str) -> str:
        field = "gx" if system.lower() == "gx" else "ghc"
        pieces: list[str] = []
        for unit in self.parse_tangut(text):
            if unit.entry:
                pieces.append(getattr(unit.entry, field) or unit.source)
            else:
                pieces.append(unit.source)
        return " ".join(x for x in pieces if x.strip())

    def _exact_candidates(self, source: str) -> list[TangutEntry]:
        candidates = list(self.cn_exact.get(_norm(source), []))
        # Prefer entries whose gloss is exactly the source, then short wordforms.
        candidates.sort(
            key=lambda e: (
                0 if _norm(e.cn) == _norm(source) else 1,
                0 if e.kind == "word" and len(source) > 1 else 1,
                len(e.key),
                e.key,
            )
        )
        return candidates

    def segment_chinese(self, text: str) -> list[ZhSegment]:
        """Segment Chinese with exact dictionary glosses using dynamic programming.

        Unknown material is kept visible instead of being replaced by an
        arbitrary Tangut glyph. Fuzzy search is deliberately *not* used here.
        """
        source = unicodedata.normalize("NFKC", text.strip())
        if not source:
            return []

        @lru_cache(maxsize=None)
        def solve(i: int):
            if i >= len(source):
                return (0.0, ())
            ch = source[i]
            if ch.isspace() or unicodedata.category(ch).startswith("P"):
                score, rest = solve(i + 1)
                return (score, (ZhSegment(ch, None, ()),) + rest)

            best_score = -1e18
            best_segments: tuple[ZhSegment, ...] = ()
            max_len = min(self.max_cn_term, len(source) - i)
            for length in range(max_len, 0, -1):
                span = source[i : i + length]
                candidates = self._exact_candidates(span)
                if not candidates:
                    continue
                tail_score, tail = solve(i + length)
                # Quadratic length reward makes exact multi-character glosses
                # dominate accidental single-character decompositions.
                local = length * length * 10.0 + (3.0 if candidates[0].kind == "word" else 0.0)
                total = local + tail_score
                if total > best_score:
                    best_score = total
                    best_segments = (ZhSegment(span, candidates[0], tuple(candidates[1:4])),) + tail
            # Transparent unknown fallback. The penalty is preferable to a
            # false dictionary translation.
            tail_score, tail = solve(i + 1)
            unknown_score = tail_score - 25.0
            if unknown_score > best_score:
                best_score = unknown_score
                best_segments = (ZhSegment(ch, None, ()),) + tail
            return best_score, best_segments

        return list(solve(0)[1])

    def translate_chinese(self, text: str) -> tuple[str, list[ZhSegment]]:
        segments = self.segment_chinese(text)
        out: list[str] = []
        for seg in segments:
            if seg.chosen:
                out.append(seg.chosen.key)
            elif seg.source.isspace() or unicodedata.category(seg.source).startswith("P"):
                out.append(seg.source)
            else:
                out.append("□")
        return "".join(out), segments


def render_tangut(text: str, font_path: Path, output_path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    text = text.strip()
    if not text:
        raise ValueError("没有可渲染的西夏文")
    if len(text) > 240:
        raise ValueError("西夏文渲染最多 240 字符")
    font = ImageFont.truetype(str(font_path), 76)
    lines: list[str] = []
    for original in text.splitlines() or [text]:
        original = original or " "
        for i in range(0, len(original), 12):
            lines.append(original[i : i + 12])
    dummy = Image.new("RGB", (10, 10), "white")
    draw = ImageDraw.Draw(dummy)
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    width = max((b[2] - b[0] for b in boxes), default=80) + 72
    line_h = max((b[3] - b[1] for b in boxes), default=80) + 28
    height = line_h * len(lines) + 56
    image = Image.new("RGB", (max(220, width), max(160, height)), "white")
    draw = ImageDraw.Draw(image)
    y = 28
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        w = box[2] - box[0]
        draw.text(((image.width - w) / 2, y), line, font=font, fill="black")
        y += line_h
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=True)
    return output_path


class CthuvianAdapter:
    """Thin adapter around the user's pinned R'lyehian/Cthuvian repository."""

    def __init__(self, checkout_root: Path):
        self.root = Path(checkout_root).resolve()
        src = str(self.root / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from cthuvian_translator import Translator
        from cthuvian_translator.reverse import ReverseGloss

        self._translator_cls = Translator
        self._reverse_cls = ReverseGloss

    def translate(self, text: str, register: str = "low") -> dict:
        result = self._translator_cls().translate(text, register=register)
        warnings = list(result.warnings)
        surface = result.cthuvian
        # Upstream deliberately supports reversible sealed tokens for material
        # outside its lexicon. That is a useful encoding mechanism, but it must
        # never be presented as if the lexicon/grammar translated the token.
        sealed_tokens = re.findall(r"zha'[^\s]*?'zhro(?:-[A-Za-z]+)?", surface)
        if "sealed_fallback" in warnings or (surface.startswith("zha'") and surface.endswith("'zhro")):
            provenance = "sealed"
        elif sealed_tokens:
            provenance = "hybrid"
        else:
            provenance = "lexicon"
        return {
            "source": result.source,
            "cthuvian": surface,
            "register": result.register,
            "roundtrip_ok": bool(result.roundtrip_ok),
            "warnings": warnings,
            "provenance": provenance,
            "sealed_tokens": len(sealed_tokens),
        }

    def gloss(self, text: str) -> dict:
        result = self._reverse_cls().gloss(text)
        return {
            "source": result.source,
            "best_gloss": result.best_gloss,
            "notes": list(result.notes),
            "analyses": [x.__dict__ for x in result.analyses],
        }


class YindianService:
    """Thin web client for Yindian, whose backend reads MCPDict.

    No MCPDict database is downloaded. Language metadata is kept only in memory
    and refreshed when its API version changes or the TTL expires.
    """

    API_BASE = "https://1305783649-j61pduj0mx.ap-guangzhou.tencentscf.com"
    _langs: list[list] | None = None
    _version: str | None = None
    _loaded_at: float = 0.0
    _lock = asyncio.Lock()

    @classmethod
    async def _get(cls, path: str, params: dict | None = None, timeout: float = 20.0) -> dict:
        headers = {"User-Agent": "Doge-v5/5.2 (+linguistics)", "Accept": "application/json"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(cls.API_BASE + path, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    @classmethod
    async def languages(cls, force: bool = False) -> tuple[str, list[list]]:
        if not force and cls._langs is not None and time.time() - cls._loaded_at < 12 * 3600:
            return cls._version or "", cls._langs
        async with cls._lock:
            if not force and cls._langs is not None and time.time() - cls._loaded_at < 12 * 3600:
                return cls._version or "", cls._langs
            payload = await cls._get("/list-langs/", timeout=25)
            cls._version = str(payload.get("version") or "")
            cls._langs = list(payload.get("data") or [])
            cls._loaded_at = time.time()
            return cls._version, cls._langs

    @staticmethod
    def _language_haystack(row: list) -> str:
        return " ".join(str(v) for v in row[1:] if v not in (None, "")).lower()

    @classmethod
    async def find_languages(cls, keyword: str, limit: int = 15) -> list[list]:
        _, rows = await cls.languages()
        q = keyword.strip().lower()
        if not q:
            return []
        scored = []
        for row in rows:
            name = str(row[1] if len(row) > 1 else "").lower()
            short = str(row[2] if len(row) > 2 else "").lower()
            hay = cls._language_haystack(row)
            if q not in hay:
                continue
            score = 0
            if q == name: score += 100
            if q == short: score += 90
            if name.startswith(q): score += 40
            if short.startswith(q): score += 35
            if q in name: score += 25
            if q in short: score += 20
            score -= len(name) * 0.02
            scored.append((score, row))
        scored.sort(key=lambda x: (-x[0], str(x[1][1])))
        return [r for _, r in scored[:limit]]

    @classmethod
    async def _resolve_one(cls, query: str) -> list | None:
        rows = await cls.find_languages(query, limit=1)
        return rows[0] if rows else None

    @staticmethod
    def _reading_text(value) -> str:
        if value in (None, ""):
            return "—"
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, list):
                    if not item: continue
                    pron = str(item[0])
                    note = str(item[1]) if len(item) > 1 and item[1] else ""
                    parts.append(pron + (f"（{note}）" if note else ""))
                else:
                    parts.append(str(item))
            return " / ".join(parts) or "—"
        return str(value)

    @classmethod
    async def readings(cls, chars: str, language_queries: list[str] | None = None) -> dict:
        chars = "".join(ch for ch in chars.strip() if not ch.isspace())
        if not chars:
            raise ValueError("缺少汉字")
        if len(chars) > 12:
            raise ValueError("一次最多比较 12 个汉字")
        lang_task = asyncio.create_task(cls.languages())
        char_task = asyncio.create_task(cls._get("/chars/", {"chars": chars}, timeout=25))
        (lang_version, langs), payload = await asyncio.gather(lang_task, char_task)
        data = list(payload.get("data") or [])
        if not data:
            raise ValueError("音典没有返回数据")
        header = [str(x) for x in data[0]]
        by_id = {int(row[0]): row for row in langs if row and str(row[0]).isdigit()}
        readings = {int(row[0]): row[1:] for row in data[1:] if row and str(row[0]).isdigit()}

        queries = language_queries or ["普通话", "北京", "广州", "上海", "苏州", "厦门", "福州", "梅县", "中古", "上古", "日语", "韩语", "越南"]
        selected: list[list] = []
        used: set[int] = set()
        for query in queries:
            matches = await cls.find_languages(query, limit=5)
            match = next((r for r in matches if int(r[0]) in readings and int(r[0]) not in used), None)
            if match is not None:
                selected.append(match); used.add(int(match[0]))
        if not selected:
            for lid in readings:
                if lid in by_id:
                    selected.append(by_id[lid])
                if len(selected) >= 12: break

        rows_out = []
        for lang in selected[:20]:
            lid = int(lang[0]); vals = readings.get(lid, [])
            rows_out.append({
                "id": lid,
                "name": str(lang[1] if len(lang) > 1 else lid),
                "short": str(lang[2] if len(lang) > 2 else ""),
                "group": str(lang[8] if len(lang) > 8 else ""),
                "location": str(lang[12] if len(lang) > 12 else ""),
                "readings": [cls._reading_text(v) for v in vals],
            })
        return {"version": str(payload.get("version") or lang_version), "chars": header[1:], "rows": rows_out}
