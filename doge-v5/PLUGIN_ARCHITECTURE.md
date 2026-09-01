# Doge v5.4 plugin architecture

A plugin is an independently meaningful user capability, not merely a Python folder. If disabling a module makes half of another feature nonsensical, the boundary is wrong; if a tiny command cannot justify a domain, it belongs in `misc`.

## Default domains

| Plugin | Surface | Responsibility |
| --- | --- | --- |
| `doge_core` | `/ver` | minimal runtime/Agent foundation; weather tool |
| `doge_math` | `/math` | safe arithmetic, bases, pi, OEIS |
| `doge_misc` | `/util` | codec, weather UI, APOD, Bing and small group-native utilities |
| `doge_typeset` | `/tex /typst /md /snippet` | technical publishing and code presentation |
| `doge_playground` | `/lab` | visual scientific experiments only |
| `doge_engineering` | `/eng` | circuits and classical control systems |
| `doge_papers` | `/paper` | DOI/literature/citation/OA workflows |
| `doge_bio` | `/bio` | protein/gene/structure/pathway/sequence workflows |
| `doge_chem` | `/chem` | structures, PubChem, ChEMBL |
| `doge_materials` | `/mat` | OPTIMADE + CIF crystal/powder XRD |
| `doge_astro` | `/astro` | SIMBAD/exoplanets/ADS |
| `doge_clinical` | `/trial` | ClinicalTrials.gov |
| `doge_linguistics` | `/lang` | Tangut, Han readings, Cthuvian, RRPL |
| `doge_ai` | `/ai` | autograd and tokenizer internals |
| `doge_cs` | `/cs` | formal languages and graph algorithms |
| `doge_lookup` | `/lookup` | grounded Wikipedia/Wikidata/Wolfram lookup |
| `doge_diagrams` | `/diagram` | Graphviz, Mermaid and Vega-Lite |
| `doge_code` | `/run` | bounded remote code execution |
| `doge_games` | `/game` | 24, Nine Men's Morris, Signal |
| `doge_alchemy` | `/fuse` | persistent concept alchemy |
| `doge_arena` | `/arena` | persistent absurd-ability arena |

`doge_shared` has no `main.py` and is not a plugin.

## Deliberately merged domains

`doge_daily` and `doge_social` were too weak to justify standalone lifecycle. Their useful parts were merged into `misc`/core. Their old directories may remain as historical development artifacts until repository cleanup, but `merged` manifest entries are never materialized.

## Legacy museum

`doge_legacy` is disabled by default. It may register a large historical surface because that is its purpose. States include `migrated`, `retired`, `offline`, `broken`, `archived`, and `sealed`; unavailable backends always return an explanation rather than fake success.

`legacy_coverage.json` guarantees every v2 rule, v3 documented domain and v4 plugin directory has a destination. Internal EPK state variables are the only entries allowed to be `internal-drop`.

## Planned domains

`doge_media`, `doge_memes`, `doge_music`, and `doge_minecraft` remain planned. A planned entry is not considered implemented and cannot enter the default materializer profile merely to increase plugin count.

## Command policy

Formal plugins register one or a few clean canonical top-level commands. Old aliases are not passed to AstrBot `alias=` and therefore do not pollute completion/help. Historical names belong in the optional Legacy plugin.
