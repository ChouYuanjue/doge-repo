from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONA = ROOT / "persona" / "doge.json"


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
    cfg.setdefault("provider_settings", {})["default_personality"] = persona["persona_id"]
    cfg["provider_settings"].setdefault("persona_pool", ["*"])
    cfg["disable_builtin_commands"] = True
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()
    install(args.runtime.resolve(), backup=not args.no_backup)
