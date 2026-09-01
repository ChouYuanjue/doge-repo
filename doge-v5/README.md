# 豆子 Doge v5

Doge v5 is a functional re-architecture of v2-v4 on **AstrBot 4.27.x / Python 3.12**, running one AstrBot instance across QQ Official and NapCat/OneBot. Historical behavior is preserved by purpose, not by blindly keeping obsolete backends.

## Product shape

- **Core/Agent foundation**: `/ver`, platform-aware presentation, weather Agent tool.
- **Math & publishing**: `/math`, `/tex`, `/typst`, `/md`, `/snippet`.
- **Scientific playground**: `/lab` for visual mathematics/physics/complex systems.
- **Engineering**: `/eng` for Schemdraw circuits and python-control analysis.
- **Research data**: `/paper`, `/bio`, `/chem`, `/mat`, `/astro`, `/trial`.
- **Language lab**: `/lang` for Tangut, MCPDict/Yindian historical readings, Cthuvian and RRPL.
- **CS/AI lab**: `/ai` for micrograd/minBPE; `/cs` for automata and PageRank.
- **Knowledge & diagrams**: `/lookup`, `/diagram`.
- **Games & group-native mechanics**: `/game`, `/fuse`, `/arena`.
- **Code execution**: `/run` through the remote compiler backend, never host RCE.
- **Misc**: `/util` for useful small capabilities that are not independent products.
- **Legacy museum**: optional `doge_legacy`, disabled by default.

## Repository layout

- `plugins/doge_*`: independent AstrBot plugins;
- `plugins/doge_shared`: reusable services/algorithms/presentation, not an AstrBot plugin;
- `plugin_manifest.json`: deployable plugin truth;
- `legacy_coverage.json`: machine-readable v2-v4 containment map;
- `feature_catalog.json` / `FEATURE_MATRIX.md`: historical product audit;
- `tools/materialize_plugins.py`: materialize default/legacy/all profiles without starting services;
- `tests/`: regression, lifecycle, history coverage and renderer tests;
- `THIRD_PARTY.md`: upstream code/dependency/license boundaries.

## Deployment

Preview the stable default profile:

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins --profile default --dry-run
```

Materialize with symlinks after validation:

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins --profile default --mode symlink --force
```

`legacy` is opt-in. `planned` and `merged` entries are never materialized.
