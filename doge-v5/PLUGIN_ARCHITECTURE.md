# Doge v5.10 plugin architecture

A plugin is an independently meaningful user capability, not merely a Python folder. Tiny useful features live in `misc`; obsolete or unstable historical surfaces live in the opt-in Legacy museum.

## Default domains

| Plugin | Surface | Responsibility |
| --- | --- | --- |
| `doge_core` | `/help /ver /status /statics` | layered help, precise identity/health/statistics, transport policy, Agent foundation |
| `doge_admin` | `/admin ...` | namespaced AstrBot builtin conversation/admin operations |
| `doge_math` | `/math` | arithmetic, bases, pi, OEIS |
| `doge_misc` | `/util` | codec, weather UI, APOD, Bing and useful small utilities |
| `doge_typeset` | `/tex /typst /md /snippet` | technical publishing and code presentation |
| `doge_playground` | `/lab` | visual mathematical/physical/complex-system experiments |
| `doge_engineering` | `/eng` | circuits and classical control systems |
| `doge_papers` | `/paper` | literature/citation/OA workflows |
| `doge_bio` | `/bio` | protein/gene/structure/pathway/sequence workflows |
| `doge_chem` | `/chem` | chemical structures, PubChem, ChEMBL |
| `doge_materials` | `/mat` | OPTIMADE + CIF crystal/powder XRD |
| `doge_astro` | `/astro` | SIMBAD/exoplanets/ADS |
| `doge_clinical` | `/trial` | ClinicalTrials.gov |
| `doge_linguistics` | `/lang` | Tangut, Han readings, Cthuvian, RRPL |
| `doge_ai` | `/ai` | autograd and tokenizer internals |
| `doge_cs` | `/cs` | formal languages and graph algorithms |
| `doge_lookup` | `/lookup` | grounded Wikipedia/Wikidata/Wolfram lookup |
| `doge_chaoli` | `/chaoli` | Chaoli read/latest/channel/floor/member/link graph through a selective local VLESS transport; search intentionally excluded from the stable surface |
| `doge_diagrams` | `/diagram` | Graphviz, Mermaid and Vega-Lite |
| `doge_code` | `/run` | bounded remote code execution |
| `doge_games` | `/game` | 24, Nine Men's Morris, Signal, Minesweeper, unique Sudoku and Roll20 dice |
| `doge_media` | `/media` | AnimeTrace recognition and local mirage-tank visual experiments |
| `doge_alchemy` | `/fuse` | persistent concept alchemy |
| `doge_arena` | `/arena` | preserved 238-card weak-power corpus, classic fights and non-destructive high-combinatorics arena |

`doge_shared` has no `main.py` and is not a plugin.

## Help and command policy

`plugins/doge_shared/resources/capability_registry.json` is the capability/command source of truth. `/help` supports category → command → subtopic drill-down; `tools/generate_help_docs.py` generates `HELP.md`, and tests require the catalog to cover every default top-level command. Formal plugins never use AstrBot `alias=` for historical names.

AstrBot builtin commands are disabled in production and wrapped under `/admin`; Doge intentionally owns the public `/help`. Bare `/reset`, `/stats`, `/provider`, etc. therefore do not compete with the product command surface.

## Transport policy

QQ Official may use Markdown. NapCat/OneBot is plain text: shared presentation helpers strip Markdown, and Core additionally instructs Agent requests to produce plain text and sanitizes final LLM Plain components as a fallback. Media components are preserved.

## Persona

The production persona is versioned in `persona/doge.json` and installed with `tools/install_runtime_profile.py`. It is a concise technical research-partner style, not a fake human identity; few-shot dialogues pin tone without scattering persona text across plugins.

## Legacy and planned domains

`doge_legacy` is disabled by default. `legacy_coverage.json` guarantees every v2 rule, v3 documented domain and v4 plugin directory has a destination. Internal EPK state nodes alone may be `internal-drop`. `doge_memes`, `doge_music`, and `doge_minecraft` remain planned until they satisfy the same implementation/test bar.
