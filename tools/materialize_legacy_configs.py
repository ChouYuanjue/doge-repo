from __future__ import annotations

import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; copy .env.example to .env first")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value
    return values


def substitute(data: bytes, values: dict[str, str]) -> bytes:
    for key, value in values.items():
        marker = f"${{{key}}}".encode("utf-8")
        if marker in data:
            if not value:
                raise ValueError(f"{key} is required by this archived configuration")
            data = data.replace(marker, value.encode("utf-8"))
    return data


def materialize_text(source: Path, target: Path, values: dict[str, str]) -> None:
    target.write_bytes(substitute(source.read_bytes(), values))


def materialize_epk(source: Path, target: Path, values: dict[str, str]) -> None:
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(target, "w") as zout:
        for info in zin.infolist():
            payload = substitute(zin.read(info.filename), values)
            clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            clone.compress_type = info.compress_type
            clone.comment = info.comment
            clone.extra = info.extra
            clone.internal_attr = info.internal_attr
            clone.external_attr = info.external_attr
            clone.create_system = info.create_system
            zout.writestr(clone, payload)


def main() -> None:
    values = load_env(ROOT / ".env")
    materialize_text(
        ROOT / "doge-v2" / "v2_epk_config.json",
        ROOT / "doge-v2" / "v2_epk_config.local.json",
        values,
    )
    materialize_text(
        ROOT / "doge-v3" / "mirai-native" / "epk" / "v3_epk_config.json",
        ROOT / "doge-v3" / "mirai-native" / "epk" / "v3_epk_config.local.json",
        values,
    )
    materialize_epk(
        ROOT / "doge-v2" / "doge-v2.epk",
        ROOT / "doge-v2" / "doge-v2.local.epk",
        values,
    )
    print("Materialized local legacy configurations.")


if __name__ == "__main__":
    main()
