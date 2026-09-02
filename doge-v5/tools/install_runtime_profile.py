from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONA = ROOT / "persona" / "doge.json"
CORE_CONFIG_NAME = "doge_core_config.json"


def load_json_bom(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_preserve_bom(path: Path, data: dict) -> None:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8-sig" if bom else "utf-8")


def install(runtime: Path, *, backup: bool = True) -> None:
    persona = json.loads(PERSONA.read_text(encoding="utf-8"))
    config_path = runtime / "data" / "cmd_config.json"
    db_path = runtime / "data" / "data_v4.db"
    if not config_path.exists() or not db_path.exists():
        raise FileNotFoundError("AstrBot runtime config/database not found")

    if backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(config_path, config_path.with_name(f"cmd_config.json.pre-v55-{stamp}"))
        shutil.copy2(db_path, db_path.with_name(f"data_v4.db.pre-v55-{stamp}"))

    cfg = load_json_bom(config_path)

    # Runtime-private absolute admins are promoted into AstrBot's framework-level
    # admins_id list.  This makes builtin/admin permission checks (including
    # /reset in shared group sessions) authoritative without committing personal
    # IDs to the public repository. Existing framework admins are preserved.
    core_config_path = runtime / "data" / "config" / CORE_CONFIG_NAME
    private_core = {}
    if core_config_path.exists():
        private_core = load_json_bom(core_config_path)
    absolute_admin_ids = [
        str(x).strip() for x in (private_core.get("absolute_admin_ids") or [])
        if str(x).strip()
    ]
    current_admins = [str(x).strip() for x in (cfg.get("admins_id") or []) if str(x).strip()]
    cfg["admins_id"] = list(dict.fromkeys(current_admins + absolute_admin_ids))

    cfg.setdefault("provider_settings", {})["default_personality"] = persona["persona_id"]
    cfg["provider_settings"].setdefault("persona_pool", ["*"])
    cfg["disable_builtin_commands"] = True

    # Chat presentation policy. AstrBot decorates segmented replies before it
    # evaluates OneBot merged-forward conversion. Its words_count_threshold is
    # an *upper* bound for segmentation, so keeping it below forward_threshold
    # yields the intended three zones: ordinary paragraph-like replies can be
    # split only at blank lines, medium replies stay one message, and genuinely
    # long OneBot replies become one merged-forward message instead of spam.
    platform_settings = cfg.setdefault("platform_settings", {})
    platform_settings["forward_threshold"] = 1200
    segmented = platform_settings.setdefault("segmented_reply", {})
    segmented.update({
        "enable": True,
        "only_llm_result": True,
        "interval_method": "random",
        "interval": "0.4,1.0",
        "words_count_threshold": 1100,
        "split_mode": "regex",
        "regex": r".*?(?:\n{2,}|\Z)",
        "content_cleanup_rule": "",
    })
    write_json_preserve_bom(config_path, cfg)

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    begin = json.dumps(persona.get("begin_dialogs") or [], ensure_ascii=False)
    tools = None if persona.get("tools") is None else json.dumps(persona["tools"], ensure_ascii=False)
    skills = None if persona.get("skills") is None else json.dumps(persona["skills"], ensure_ascii=False)
    with sqlite3.connect(db_path) as conn:
        exists = conn.execute("SELECT 1 FROM personas WHERE persona_id=?", (persona["persona_id"],)).fetchone()
        if exists:
            conn.execute(
                "UPDATE personas SET updated_at=?, system_prompt=?, begin_dialogs=?, tools=?, skills=?, custom_error_message=? WHERE persona_id=?",
                (now, persona["system_prompt"], begin, tools, skills, persona.get("custom_error_message"), persona["persona_id"]),
            )
        else:
            conn.execute(
                "INSERT INTO personas(created_at,updated_at,persona_id,system_prompt,begin_dialogs,tools,skills,custom_error_message,folder_id,sort_order) VALUES(?,?,?,?,?,?,?,?,NULL,0)",
                (now, now, persona["persona_id"], persona["system_prompt"], begin, tools, skills, persona.get("custom_error_message")),
            )
        conn.commit()

    print(f"persona={persona['persona_id']}")
    print("default_personality=" + cfg["provider_settings"]["default_personality"])
    print("disable_builtin_commands=" + str(cfg["disable_builtin_commands"]).lower())
    print("absolute_admins_applied=" + str(len(absolute_admin_ids)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()
    install(args.runtime.resolve(), backup=not args.no_backup)
