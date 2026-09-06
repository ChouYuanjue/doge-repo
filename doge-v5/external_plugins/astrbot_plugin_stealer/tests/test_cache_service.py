import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path


def _install_stubs():
    if "astrbot.api" in sys.modules:
        return

    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )

    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    api_module.logger = logger
    event_module = types.ModuleType("astrbot.api.event")
    event_module.AstrMessageEvent = type("AstrMessageEvent", (), {})
    event_module.MessageChain = list
    star_module = types.ModuleType("astrbot.api.star")
    star_module.Context = object
    star_module.StarTools = types.SimpleNamespace(
        get_data_dir=lambda name: str(Path(tempfile.gettempdir()) / "astrbot_test" / name)
    )
    message_components_module = types.ModuleType("astrbot.api.message_components")
    message_components_module.Image = type("Image", (), {})
    message_components_module.Plain = type("Plain", (), {})

    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.star"] = star_module
    sys.modules["astrbot.api.message_components"] = message_components_module


_install_stubs()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cache_service import CacheService


def test_migrate_legacy_data_returns_loaded_records(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    backup_path = cache_dir / "index_cache.json.backup"
    legacy_index = {
        "/legacy/a.gif": {
            "hash": "h1",
            "category": "happy",
            "desc": "legacy-desc",
            "tags": ["legacy-tag"],
            "scenes": ["legacy-scene"],
        }
    }
    backup_path.write_text(json.dumps(legacy_index, ensure_ascii=False), encoding="utf-8")

    service = CacheService(cache_dir=cache_dir)
    migrated = asyncio.run(service.migrate_legacy_data(tmp_path))

    assert migrated == legacy_index
    # v2.7.5+ 起 cache_service 不再缓存 index 数据；调用方负责写入 DB。
    assert service.get_cache("index_cache") == {}


def test_load_legacy_index_data_prefers_richer_metadata(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    primary_path = cache_dir / "index_cache.json"
    backup_path = cache_dir / "index_cache.json.backup"
    primary_path.write_text(
        json.dumps(
            {
                "/legacy/a.gif": {
                    "hash": "h1",
                    "category": "happy",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    backup_path.write_text(
        json.dumps(
            {
                "/legacy/a.gif": {
                    "hash": "h1",
                    "category": "happy",
                    "desc": "rich-desc",
                    "tags": ["rich-tag"],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = CacheService(cache_dir=cache_dir)
    merged, loaded_paths = asyncio.run(service.load_legacy_index_data(tmp_path))

    assert primary_path in loaded_paths
    assert backup_path in loaded_paths
    assert merged["/legacy/a.gif"]["desc"] == "rich-desc"
    assert merged["/legacy/a.gif"]["tags"] == ["rich-tag"]


def test_no_index_cache_bucket_exists():
    """v2.7.5+ 起 index_cache 不再是 CacheService 管理的 bucket。"""
    from cache_service import CacheService
    service = CacheService(cache_dir=Path("/tmp/_cache_service_test_no_index"))
    assert "index_cache" not in service._caches
