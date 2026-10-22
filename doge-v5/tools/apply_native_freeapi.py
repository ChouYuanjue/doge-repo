"""Safely stage/apply Doge's *native AstrBot* provider configuration.

Doge Agent Runner, persona, history, prompt and tools are intentionally
untouched. Upstream FreeLLMAPI's strategy is untouched as well.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

from native_freeapi_provider import configure_native_freeapi

CONFIG = Path("/root/doge-runtime/data/cmd_config.json")
BACKUP_DIR = Path("/root/doge-runtime/backups")
BACKUP = BACKUP_DIR / "cmd_config.before-workbuddy-native-20261022.json"
RECORD = BACKUP_DIR / "cmd_config.native-workbuddy-20261022.sha256"
DB = "file:/var/lib/freellmapi-lab/freeapi.db?mode=ro"
ENV = Path("/etc/workbuddy-lab/runtime.env")


def _key_from_workbuddy():
    for line in ENV.read_text().splitlines():
        if line.startswith("WB_PROXY_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError("WorkBuddy local key missing")


def _build():
    original_bytes = CONFIG.read_bytes()
    original = json.loads(original_bytes.decode("utf-8-sig"))
    with sqlite3.connect(DB, uri=True) as db:
        unified_row = db.execute("SELECT value FROM settings WHERE key='unified_api_key'").fetchone()
    if not unified_row:
        raise ValueError("FreeLLMAPI unified key not initialized")
    proposed = configure_native_freeapi(
        original, unified_key=unified_row[0],
        workbuddy_key=_key_from_workbuddy(), activate=True,
    )
    models = [p.get("id") for p in proposed["provider"]]
    assert len(set(models)) == len(models), "duplicate model registration"
    source_ids = [s.get("id") for s in proposed["provider_sources"]]
    assert len(set(source_ids)) == len(source_ids), "duplicate source registration"
    assert "deepseek/deepseek-v4-flash" in proposed["provider_settings"]["fallback_chat_models"]
    assert proposed["provider_settings"]["default_provider_id"] == "workbuddy/deepseek-v4.1-flash"
    # The complete config outside AstrBot provider arrays and provider_settings
    # must retain its exact parsed meaning, not merely the same persona string.
    reserved = {"provider_sources", "provider", "provider_settings"}
    for key in set(original) | set(proposed):
        if key not in reserved:
            assert proposed.get(key) == original.get(key), f"Unexpected config rewrite {key}"
    data = json.dumps(proposed, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    return original_bytes, data, proposed


def _atomic_bytes(destination, data, mode):
    fd, path = tempfile.mkstemp(prefix=".native-provider-", dir=destination.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(path, destination)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--rollback", action="store_true")
    args = p.parse_args()
    if args.apply and args.rollback:
        p.error("choose one action")
    if args.rollback:
        if not BACKUP.exists() or not RECORD.exists():
            raise SystemExit("No matching original config backup")
        expected = RECORD.read_text().strip()
        actual = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
        if expected != actual:
            raise SystemExit("Current AstrBot config differs from applied candidate: refusing unsafe rollback")
        original = BACKUP.read_bytes()
        _atomic_bytes(CONFIG, original, 0o600)
        print("ROLLED_BACK_TO_ORIGINAL_ASTRBOT_CONFIG")
        return

    old, new, candidate = _build()
    print("NATIVE_CONFIG_PREFLIGHT_OK")
    print("provider_sources_total", len(candidate["provider_sources"]),
          "models_total", len(candidate["provider"]))
    print("model_default", candidate["provider_settings"]["default_provider_id"])
    print("native_fallback_models", candidate["provider_settings"]["fallback_chat_models"])
    print("original_digest_prefix", hashlib.sha256(old).hexdigest()[:12])
    if not args.apply:
        print("DRY_RUN_ONLY")
        return
    if BACKUP.exists() or RECORD.exists():
        raise SystemExit("Backup already exists; refusing repeated deployment")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_bytes(BACKUP, old, 0o600)
    _atomic_bytes(CONFIG, new, 0o600)
    _atomic_bytes(RECORD, (hashlib.sha256(new).hexdigest()+"\n").encode(), 0o600)
    assert CONFIG.read_bytes() == new
    print("ASTRBOT_NATIVE_CONFIGURATION_APPLIED")
    print("rollback_command: python3.11 doge-v5/tools/apply_native_freeapi.py --rollback")


if __name__ == "__main__":
    main()
