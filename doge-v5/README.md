# 豆子 Doge v5

Doge v5 is a functional re-architecture of v2-v4 on **AstrBot 4.27.x / Python 3.12**, running one AstrBot instance across QQ Official and NapCat/OneBot. Historical behavior is preserved by purpose, not by blindly keeping obsolete backends.

## Product shape

- **Core/Agent foundation**: `/help`, `/ver`, `/status`, `/statics`, transport-aware presentation and weather Agent tool.
- **Framework administration**: AstrBot builtin operations are isolated under `/admin ...`; bare builtin commands are disabled in production.
- **Math & publishing**: `/math`, `/tex`, `/typst`, `/md`, `/snippet`.
- **Scientific/engineering playground**: `/lab`, `/eng`.
- **Research data**: `/paper`, `/bio`, `/chem`, `/mat`, `/astro`, `/trial`.
- **Language lab**: `/lang` for Tangut, MCPDict/Yindian historical readings, Cthuvian and RRPL.
- **CS/AI lab**: `/ai` for micrograd/minBPE; `/cs` for automata and PageRank.
- **Knowledge & diagrams**: `/lookup`, `/diagram`.
- **Games & group-native mechanics**: `/game` (24, Morris, Signal, Minesweeper, Sudoku, Roll20 dice), `/fuse`, `/arena`.
- **Media experiments**: `/media` for AnimeTrace and local mirage images.
- **Code execution**: `/run` through the remote compiler backend, never host RCE.
- **Misc**: `/util` for useful small capabilities that are not independent products.
- **Legacy museum**: optional `doge_legacy`, disabled by default.

See **`HELP.md`** for the generated layered command guide, **`PERSONA.md`** for the versioned production persona, and **`TRUTHFULNESS.md`** for the no-silent-mock result policy.

## Repository layout

- `plugins/doge_*`: independent AstrBot plugins;
- `plugins/doge_shared`: reusable services/algorithms/presentation, not an AstrBot plugin;
- `plugin_manifest.json`: deployable plugin truth;
- `plugins/doge_shared/resources/help_catalog.json`: command-help source of truth;
- `persona/doge.json`: production persona source of truth;
- `legacy_coverage.json`: machine-readable v2-v4 containment map;
- `feature_catalog.json` / `FEATURE_MATRIX.md`: historical product audit;
- `tools/materialize_plugins.py`: materialize default/legacy/all profiles;
- `tools/install_runtime_profile.py`: install persona and runtime command policy;
- `tests/`: regression, lifecycle, history coverage and renderer tests;
- `THIRD_PARTY.md`: upstream code/dependency/license boundaries.

## Deployment

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins --profile default --dry-run
```

After validation, materialize the profile and install runtime policy/persona:

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins --profile default --mode symlink --force
python3 doge-v5/tools/install_runtime_profile.py --runtime /path/to/AstrBot
```

`legacy` is opt-in. `planned` and `merged` entries are never materialized.
