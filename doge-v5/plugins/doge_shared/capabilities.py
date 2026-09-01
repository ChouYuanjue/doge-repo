from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name("resources") / "capability_registry.json"


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def formal_operations() -> list[dict]:
    return list(registry().get("operations", []))


def legacy_operations() -> list[dict]:
    return list((registry().get("legacy") or {}).get("operations", []))


@dataclass(frozen=True, slots=True)
class Invocation:
    capability_id: str
    canonical: str
    invoked: str
    is_alias: bool
    kind: str = "command"


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(x.lower() for x in text.strip().split() if x)


def _mode_ok(mode: str, extra: int) -> bool:
    if mode == "none":
        return extra == 0
    if mode == "required":
        return extra >= 1
    return extra >= 0


def match_invocation(message: str, *, include_legacy: bool = False) -> Invocation | None:
    """Recognize only designed Doge invocations.

    `/` is a wake prefix in production.  Therefore arbitrary `/anything ...`
    messages must *not* become command usage just because they woke AstrBot.
    Aliases collapse to one canonical capability ID.
    """
    raw = (message or "").strip()
    ops = formal_operations()
    if include_legacy:
        ops += legacy_operations()

    if not raw.startswith("/"):
        for op in ops:
            if op.get("kind") == "trigger" and re.search(op.get("pattern", r"$^"), raw):
                return Invocation(op["id"], op["path"], op["usage"], False, "trigger")
        return None

    body = raw[1:].strip()
    if not body:
        return None
    toks = _tokens(body)
    if not toks:
        return None

    # Top-level help requests are navigation, not usage of the underlying leaf.
    # `/admin help` is itself a real administrative command and stays countable.
    if len(toks) >= 2 and toks[1] in {"help", "?"} and toks[0] not in {"help", "admin"}:
        return None

    candidates: list[tuple[tuple[int, int, int], Invocation]] = []
    for op in ops:
        if op.get("kind", "command") != "command":
            continue
        canonical = op["path"]
        forms = [(canonical, False)] + [(x, True) for x in op.get("aliases", [])]
        mode = op.get("args", "required")
        for form, is_alias in forms:
            ft = _tokens(form)
            if len(toks) < len(ft) or toks[: len(ft)] != ft:
                continue
            extra = len(toks) - len(ft)
            if not _mode_ok(mode, extra):
                continue
            specificity = {"none": 3, "required": 2, "optional": 1}.get(mode, 0)
            score = (len(ft), specificity, 0 if is_alias else 1)
            candidates.append((score, Invocation(op["id"], canonical, form, is_alias)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    inv = candidates[0][1]

    # Documented convenience syntax: `/trial NCT...` means trial.get.
    if inv.capability_id == "trial.search" and len(toks) >= 2 and toks[0] == "trial" and toks[1].upper().startswith("NCT"):
        return Invocation("trial.get", "trial get", "trial", True)
    return inv


def counts() -> dict[str, int]:
    d = registry()
    formal = formal_operations()
    legacy = legacy_operations()
    formal_forms = sum(1 + len(x.get("aliases", [])) for x in formal)
    legacy_forms = sum(1 + len(x.get("aliases", [])) for x in legacy)
    legacy_commands = (d.get("legacy") or {}).get("commands", {})
    return {
        "top_level": len(d.get("commands", {})),
        "functions": len(formal),
        "forms": formal_forms,
        "aliases": formal_forms - len(formal),
        "triggers": sum(1 for x in formal if x.get("kind") == "trigger"),
        "legacy_top_level": len(legacy_commands),
        "legacy_functions": len(legacy),
        "legacy_forms": legacy_forms,
        "all_functions": len(formal) + len(legacy),
    }


def operation_by_id(capability_id: str) -> dict | None:
    return next((x for x in formal_operations() + legacy_operations() if x["id"] == capability_id), None)


def operations_for_prefix(prefix: str, *, legacy: bool = False) -> list[dict]:
    p = " ".join(prefix.lower().split())
    ops = legacy_operations() if legacy else formal_operations()
    return [
        x
        for x in ops
        if x.get("kind", "command") == "command"
        and (x["path"] == p or x["path"].startswith(p + " "))
    ]


def suggestions(topic: str, n: int = 4) -> list[str]:
    d = registry()
    normalized = " ".join(topic.lower().split())
    legacy = d.get("legacy") or {}
    if normalized.startswith("legacy "):
        keys = ["legacy " + x for x in legacy.get("commands", {})]
        keys += ["legacy " + x["path"] for x in legacy_operations()]
    else:
        keys = list(d.get("commands", {}))
        keys += [x["id"] for x in d.get("categories", [])]
        keys += [x["path"] for x in formal_operations() if x.get("kind", "command") == "command"]
        keys.append("legacy")
    return get_close_matches(normalized, keys, n=n, cutoff=0.42)


def capability_display(capability_id: str) -> str:
    op = operation_by_id(capability_id)
    if not op:
        return capability_id
    return "/" + op["path"] if op.get("kind", "command") == "command" else op["usage"]


def _agent_input_hint(op: dict) -> str:
    inputs = [x for x in (op.get("inputs") or []) if isinstance(x, dict)]
    if not inputs:
        return ""
    required = [str(x.get("name") or "<attachment>") for x in inputs if x.get("required", True)]
    optional = [str(x.get("name") or "<attachment>") for x in inputs if not x.get("required", True)]
    bits = []
    if required:
        bits.append("requires same-message input: " + ", ".join(required))
    if optional:
        bits.append("optional same-message input: " + ", ".join(optional))
    return " [" + "; ".join(bits) + "]" if bits else ""


def _search_terms(query: str) -> list[str]:
    text = str(query or "").lower().strip()
    words = re.findall(r"[a-z0-9_+#.\-]+|[\u4e00-\u9fff]+", text)
    terms: set[str] = set()
    for word in words:
        if not word:
            continue
        terms.add(word)
        if re.fullmatch(r"[\u4e00-\u9fff]+", word) and len(word) >= 2:
            # Chinese user queries rarely contain spaces, so character n-grams
            # make natural-language search useful without embeddings or another LLM.
            for n in (2, 3, 4):
                if len(word) >= n:
                    terms.update(word[i:i+n] for i in range(len(word)-n+1))
    return sorted(terms, key=lambda x: (-len(x), x))


def search_capabilities(query: str, limit: int = 8) -> list[dict]:
    """Search formal capability leaves using registry text only.

    This is deliberately deterministic and dependency-free.  It is used by the
    Agent as an on-demand index so the complete 200+ leaf manual no longer has
    to occupy every chat turn.
    """
    q = str(query or "").strip().lower()
    if not q:
        return []
    terms = _search_terms(q)
    semantic_aliases = {
        "翻译": ("translate", "translation", "zh2t", "t2zh"),
        "西夏": ("tangut",),
        "积分": ("integrate", "integral"),
        "求导": ("diff", "derivative"),
        "微分": ("diff", "derivative"),
        "方程": ("solve", "equation"),
        "素数": ("prime",),
        "因数": ("factor", "factorint"),
        "因式分解": ("factor",),
        "生命游戏": ("life", "conway"),
        "动图": ("gif",),
        "晶体": ("crystal",),
        "形式化": ("formal",),
        "证明": ("formal", "lean", "coq", "rzk"),
        "傅里叶": ("fourier", "dft", "epicycle"),
        "傅立叶": ("fourier", "dft", "epicycle", "傅里叶"),
        "旋转圆": ("fourier", "epicycle"),
        "轮廓描图": ("fourier", "image", "epicycle"),
    }
    expanded: set[str] = set(terms)
    for key, values in semantic_aliases.items():
        if key in q:
            expanded.update(values)
    terms = sorted(expanded, key=lambda x: (-len(x), x))
    ranked: list[tuple[float, str, dict]] = []
    for op in formal_operations():
        if op.get("kind", "command") != "command":
            continue
        path = str(op.get("path") or "").lower()
        usage = str(op.get("usage") or "").lower()
        summary = str(op.get("summary") or "").lower()
        notes = str(op.get("agent_notes") or "").lower()
        aliases = " ".join(str(x) for x in op.get("aliases", [])).lower()
        params = " ".join(
            f"{x.get('name','')} {x.get('description','')}"
            for x in (op.get("parameters") or []) if isinstance(x, dict)
        ).lower()
        inputs = " ".join(
            f"{x.get('name','')} {x.get('description','')}"
            for x in (op.get("inputs") or []) if isinstance(x, dict)
        ).lower()
        hay = " ".join((path, usage, summary, notes, aliases, params, inputs))
        score = 0.0
        if q == path or q == usage.lstrip("/"):
            score += 80
        if q and q in path:
            score += 35
        if q and q in summary:
            score += 26
        for term in terms:
            if len(term) == 1:
                continue
            weight = min(8.0, 2.0 + len(term) * .8)
            if term in path: score += weight * 2.2
            if term in usage: score += weight * 1.8
            if term in summary: score += weight * 1.5
            if term in notes: score += weight * 1.2
            if term in params or term in inputs: score += weight
            if term in aliases: score += weight
        if score > 0:
            ranked.append((score, path, op))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for score, _, op in ranked[: max(1, min(int(limit), 12))]:
        item = {
            "id": op["id"],
            "command": "/" + op["path"],
            "usage": op["usage"],
            "summary": op.get("summary", ""),
            "score": round(score, 2),
        }
        if op.get("parameters"):
            item["parameters"] = op["parameters"]
        if op.get("inputs"):
            item["inputs"] = op["inputs"]
        if op.get("examples"):
            item["examples"] = op["examples"][:3]
        if op.get("agent_notes"):
            item["agent_notes"] = op["agent_notes"]
        out.append(item)
    return out


@lru_cache(maxsize=1)
def agent_capability_prompt() -> str:
    """Compact capability map injected into every Agent request.

    Leaf-level syntax is available on demand through doge_capability_search.
    Keeping this map short materially improves ordinary chat and reasoning while
    preserving discoverability of the complete formal registry.
    """
    d = registry()
    c = counts()
    lines = [
        "# Doge capability map",
        "Capability truth comes from the same registry as /help. Do not guess that a function is unavailable.",
        f"Installed formal surface: {c['top_level']} top-level groups / {c['functions']} canonical leaf functions / {c['forms']} callable forms.",
        "For a specific function or exact syntax, call doge_capability_search once in the user's language, then call doge_capability using the returned documented command. Search again only if candidates are ambiguous; do not duplicate the same search bilingually. Prefer a dedicated domain tool when it already matches the task.",
        "doge_capability may return deferred media asset IDs; call doge_present only for images that materially improve the answer.",
        "Current session module switches take precedence. Legacy is historical and is not callable by default.",
        "",
        "Top-level map:",
    ]
    for cmd, meta in d.get("commands", {}).items():
        lines.append(f"/{cmd} — {meta.get('summary','')}")
    lines += [
        "",
        "Examples of discovery: search ‘西夏文 翻译’ before Tangut work; ‘RRPL 语法’; ‘符号积分’; ‘生命游戏 GIF’; ‘CIF 晶体’; ‘Lean 形式化’.",
        "When users ask what Doge can do broadly, summarize categories from this map. When they ask about one concrete ability, search rather than dumping the entire registry.",
    ]
    return "\n".join(lines)
