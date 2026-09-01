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


@lru_cache(maxsize=1)
def agent_capability_prompt() -> str:
    """Complete capability inventory injected into every Agent request.

    The inventory is deliberately leaf-level.  The model should know that, for
    example, Tangut is not merely a dictionary lookup but includes both
    translation directions, two pronunciation systems, and rendering.
    """
    d = registry()
    by_command: dict[str, list[dict]] = {}
    for op in formal_operations():
        if op.get("kind") == "trigger":
            continue
        top = op["path"].split()[0]
        by_command.setdefault(top, []).append(op)

    c = counts()
    lines = [
        "# Doge capability inventory",
        "This is authoritative runtime self-knowledge generated from the same registry as /help and /statics.",
        "Do not claim an installed capability is unavailable until you have checked this list.",
        "Every installed formal non-Legacy capability below is callable by the Agent: prefer a dedicated Doge domain tool when one exists, otherwise invoke the exact documented command through doge_capability.",
        "The Agent is the synthesis layer above plugin outputs. It may combine several capabilities, reconcile or summarize their text results, and should show only the most useful evidence instead of dumping every raw result.",
        "doge_capability can return deferred media asset IDs. Call doge_present only for images that materially improve the answer; do not automatically present every image produced by tools.",
        "If seeing the exact raw plugin output would help, you may optionally mention its complete canonical/direct command. Do not append command reminders to every answer.",
        "When a user asks whether Doge can do something, answer from this inventory. Current group module switches can temporarily make an installed module unavailable and take precedence over this global inventory.",
        "Important example: Tangut support includes dictionary lookup, GX/GHC pronunciation, Tangut→Chinese, Chinese→Tangut, and image rendering.",
        "",
        f"Installed formal surface: {c['top_level']} top-level commands; {c['functions']} canonical leaf functions; {c['forms']} callable forms including aliases.",
    ]
    for cmd in d.get("commands", {}):
        ops = by_command.get(cmd, [])
        if not ops:
            continue
        lines.append(f"/{cmd}: " + d["commands"][cmd].get("summary", ""))
        for op in ops:
            note = str(op.get("agent_notes") or "").strip()
            suffix = _agent_input_hint(op)
            if note:
                suffix += " Agent note: " + note
            lines.append(f"  {op['usage']} — {op['summary']}{suffix}")
    triggers = [x for x in formal_operations() if x.get("kind") == "trigger"]
    if triggers:
        lines.append("Designed non-slash triggers:")
        for op in triggers:
            lines.append(f"  {op['usage']} — {op['summary']}")

    legacy = d.get("legacy") or {}
    if legacy:
        lines += [
            "",
            f"Legacy museum: {c['legacy_top_level']} historical top-level entries / {c['legacy_functions']} documented historical leaf functions.",
            "Legacy is NOT loaded by the default profile. Know what existed and its migration state, but do not claim those historical commands are currently executable unless the Legacy plugin is explicitly enabled.",
        ]
        for cmd, meta in legacy.get("commands", {}).items():
            lines.append(f"  /{cmd} [{meta.get('state','legacy')}] — {meta.get('title','historical feature')}")
    return "\n".join(lines)
