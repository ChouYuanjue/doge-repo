from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LANGUAGE_VERSION = "RC-1.0"


def normalize_english(text: str) -> str:
    text = str(text or "").replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).strip().lower())


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    source: str
    rc: str
    strategy: str
    metadata: dict[str, Any]


class PersistentCthuvianRegistry:
    """Upstream fixed/generated registry layers + Doge learned terms."""

    def __init__(self, checkout_root: Path, learned_path: Path | None = None) -> None:
        self.root = Path(checkout_root).resolve()
        self.learned_path = Path(learned_path).resolve() if learned_path else None
        self._lock = threading.RLock()
        self._static: dict[str, RegistryEntry] = {}
        self._learned: dict[str, RegistryEntry] = {}
        self._load_static()
        self._reload_learned()

    def _load_static(self) -> None:
        seed = self.root / "data" / "registry.json"
        if seed.exists():
            payload = json.loads(seed.read_text(encoding="utf-8"))
            for source, item in payload.get("entries", {}).items():
                self._static[normalize_english(source)] = RegistryEntry(
                    str(source), str(item["rc"]), str(item.get("strategy") or "core_registry"),
                    {k: v for k, v in item.items() if k != "rc"},
                )
        generated = self.root / "data" / "generated" / "common-generated-report.json"
        if generated.exists():
            for item in json.loads(generated.read_text(encoding="utf-8")):
                source = str(item.get("source_base") or "").strip()
                rc = str(item.get("rc") or "").strip()
                if source and rc:
                    self._static.setdefault(normalize_english(source), RegistryEntry(
                        source, rc, str(item.get("strategy") or "generated_common"),
                        {"roots": list(item.get("roots") or []), "evidence": list(item.get("evidence") or []),
                         "literal_gloss": source, "generated_common": True},
                    ))

    def _payload(self) -> dict[str, Any]:
        if self.learned_path is None or not self.learned_path.exists():
            return {"language_version": LANGUAGE_VERSION, "entries": {}}
        payload = json.loads(self.learned_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("entries", {}), dict):
            raise ValueError("malformed Cthuvian learned registry")
        if payload.get("language_version", LANGUAGE_VERSION) != LANGUAGE_VERSION:
            raise ValueError("Cthuvian registry language version mismatch")
        payload.setdefault("language_version", LANGUAGE_VERSION)
        payload.setdefault("entries", {})
        return payload

    @staticmethod
    def _decode(payload: dict[str, Any]) -> dict[str, RegistryEntry]:
        out: dict[str, RegistryEntry] = {}
        for source, item in payload.get("entries", {}).items():
            if isinstance(item, dict) and item.get("rc"):
                out[normalize_english(source)] = RegistryEntry(
                    str(source), str(item["rc"]), str(item.get("strategy") or "learned"),
                    {k: v for k, v in item.items() if k != "rc"},
                )
        return out

    def _reload_learned(self) -> None:
        self._learned = self._decode(self._payload())

    def lookup(self, source: str) -> RegistryEntry | None:
        key = normalize_english(source)
        with self._lock:
            return self._learned.get(key) or self._static.get(key)

    def learned_count(self) -> int:
        with self._lock:
            self._reload_learned()
            return len(self._learned)

    def learned_bytes(self) -> bytes:
        return self.learned_path.read_bytes() if self.learned_path and self.learned_path.exists() else b""

    def all_entries(self) -> dict[str, RegistryEntry]:
        with self._lock:
            self._reload_learned()
            return {**self._static, **self._learned}

    def reverse_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for source, entry in self.all_entries().items():
            out.setdefault(normalize_english(entry.rc), str(entry.metadata.get("literal_gloss") or source))
        return out

    def accept(self, source: str, rc: str, *, strategy: str, literal_gloss: str,
               components: Iterable[str] = (), concept_type: str | None = None,
               model_profile: str | None = None, validator_report: dict[str, Any] | None = None) -> tuple[RegistryEntry, bool]:
        key, rc = normalize_english(source), str(rc or "").strip().lower()
        if not key or not rc:
            raise ValueError("empty Cthuvian registry source or surface")
        if self.learned_path is None:
            raise ValueError("Cthuvian learned registry path is not configured")
        with self._lock:
            payload = self._payload()
            self._learned = self._decode(payload)
            existing = self._learned.get(key) or self._static.get(key)
            if existing:
                return existing, False
            target = normalize_english(rc)
            collisions = {src for src, ent in {**self._static, **self._learned}.items()
                          if normalize_english(ent.rc) == target and src != key}
            if collisions:
                raise ValueError(f"Cthuvian term collision: {rc} already maps to {', '.join(sorted(collisions)[:5])}")
            item: dict[str, Any] = {
                "rc": rc, "strategy": strategy, "literal_gloss": literal_gloss or key,
                "components": list(components), "concept_type": concept_type,
                "created_by": "doge.deepseek.high", "accepted": True, "language_version": LANGUAGE_VERSION,
                "accepted_at": datetime.now(timezone.utc).isoformat(),
            }
            if model_profile:
                item["model_profile"] = model_profile
            if validator_report:
                item["validator_report"] = validator_report
            payload["entries"][key] = item
            self.learned_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.learned_path.with_name(self.learned_path.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, self.learned_path)
            self._reload_learned()
            return self._learned[key], True


class UpstreamProposalRules:
    """Mirror upstream production validateTermProposal(), roots read from upstream data."""

    def __init__(self, checkout_root: Path) -> None:
        payload = json.loads((Path(checkout_root) / "data" / "rc1-root-glosses.json").read_text(encoding="utf-8"))
        self.roots = {str(k): {"surface": str(v["surface"]), "keywords": list(v.get("keywords") or [])}
                      for k, v in payload.items() if v.get("surface")}

    def validate(self, proposal: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(proposal, dict):
            return {"ok": False, "reason": "proposal_not_object"}
        selected = list(proposal.get("selected_roots")) if isinstance(proposal.get("selected_roots"), list) else []
        if selected:
            if len(selected) > 6:
                return {"ok": False, "reason": "too_many_selected_roots"}
            for root in selected:
                if root not in self.roots:
                    return {"ok": False, "reason": f"unknown_root:{root}"}
            term = "-".join(self.roots[root]["surface"] for root in selected)
            probe = term.replace("kadishtu", "").replace("phlegeth", "").replace("shuggoth", "")
            if not term or re.search(r"[A-Za-z]{12,}", probe):
                return {"ok": False, "reason": "phonotactic_or_leakage_failure"}
            return {"ok": True, "term": term, "strategy": "semantic_compound"}
        coined = str(proposal.get("coined_surface") or "").strip().lower()
        source = str(proposal.get("source_term") or "")
        if proposal.get("needs_new_root") and coined:
            check = self._validate_coined(coined, source)
            if not check["ok"]:
                return check
            return {"ok": True, "term": coined, "strategy": "llm_coined_surface"}
        return {"ok": False, "reason": "new_root_without_valid_surface" if proposal.get("needs_new_root") else "bad_selected_roots"}

    @staticmethod
    def _validate_coined(surface: str, source: str) -> dict[str, Any]:
        if len(surface) < 3 or len(surface) > 40:
            return {"ok": False, "reason": "coined_length_invalid"}
        if not re.fullmatch(r"[a-z][a-z' -]*[a-z]", surface):
            return {"ok": False, "reason": "coined_characters_invalid"}
        if "'" not in surface and not re.search(r"cth|fht|mgl|ngl|th|gh|kh|sh|ll|rr", surface):
            return {"ok": False, "reason": "coined_not_cthuvian_enough"}
        clean_surface = re.sub(r"[^a-z]", "", surface)
        clean_source = re.sub(r"[^a-z]", "", source.lower())
        for size in range(5, min(len(clean_source), len(clean_surface)) + 1):
            for index in range(len(clean_source) - size + 1):
                if clean_source[index:index + size] in clean_surface:
                    return {"ok": False, "reason": "coined_english_leakage"}
        return {"ok": True}

    def proposal_prompt(self, source_term: str, context_text: str, rejection_reason: str = "") -> tuple[str, str]:
        compact = {rid: {"surface": item["surface"], "keywords": item.get("keywords", [])} for rid, item in self.roots.items()}
        system = (
            "You are the constrained terminology proposal layer for RC-1 high-register Cthuvian. Return JSON only. "
            "Prefer a semantic compound made only from the provided root IDs. If the concept cannot be represented by those roots, set needs_new_root=true and propose one coined_surface. "
            "A coined surface must be one compact RC-1 lexical token rather than English transliteration: lowercase ASCII letters/apostrophes/hyphens only (use hyphens, never spaces), with an apostrophe or a cluster like cth/fht/mgl/ngl/th/gh/kh/sh/ll/rr. "
            "Do not preserve long English substrings or change the source concept. Deterministic rules and registry uniqueness decide acceptance."
        )
        retry = f"\nPREVIOUS REJECTION: {rejection_reason}\nPropose a different construction." if rejection_reason else ""
        prompt = (
            "Return one JSON object with keys source_term, concept_type, selected_roots, literal_gloss, needs_new_root, coined_surface. "
            "concept_type is object/person/place/instrument/abstract/event; coined_surface is empty unless needs_new_root=true.\n"
            f"SOURCE_TERM: {source_term}\nCONTEXT: {context_text}\nROOTS: {json.dumps(compact, ensure_ascii=False)}{retry}"
        )
        return system, prompt
