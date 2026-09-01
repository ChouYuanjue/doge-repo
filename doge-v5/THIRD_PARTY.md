# Doge v5 third-party notes

Doge distinguishes **runtime dependency**, **pinned upstream submodule**, **vendored release artifact**, and **implementation reference only**. This keeps normal dependencies normal and prevents accidental forks or unattributed source copies.

## Pinned upstream submodules

- `karpathy/micrograd` — MIT — `7bc720e951fe422b8f8814aa5aa1b64121d26b4c`; `/ai grad`.
- `karpathy/minbpe` — MIT — `1acefe89412b20245db5a22d2a02001e547dc602`; `/ai bpe`.
- `Aunsiels/pyformlang` — MIT — `8ecb156f662609c56bb3ee7a7e5151bf77c10e16`; `/cs regex`.
- `ChouYuanjue/Rlyehian-Cthuvian-Translator` — MIT — `0a62c9490c92d035fa09aaadaa156de86cab5cda`; `/lang cthuvian`. Doge uses the source checkout because the current upstream wheel assumes repository-relative data files.
- `Dherse/codly` — MIT — `93bf59d43deff1431df889995b1427350eeb1499` (release 1.3.0); `/snippet`.

Their license files remain in each submodule.

## Vendored Typst Universe release artifacts

`plugins/doge_shared/vendor/` contains the exact official Typst Universe release artifacts needed for offline Markdown rendering:

- cmarker `0.1.10`;
- MiTeX `0.2.7`.

The packaged releases are used instead of rebuilding from Git tags because the Git trees do not necessarily contain the released WASM artifacts. Their bundled LICENSE files must remain.

## Runtime dependencies

No source is copied for these packages:

- Typst Python binding and `resvg_py` — `/typst`, `/md`, `/snippet`, TeX SVG→PNG;
- Schemdraw — MIT — `/eng circuit`;
- python-control — BSD-3-Clause — `/eng control`;
- SciPy and Matplotlib — engineering and diffraction numerical/plotting runtime;
- Dans_Diffraction — Apache-2.0 — `/mat crystal`;
- NetworkX + pydot + system Graphviz — PageRank and local graph/automata rendering;
- `vl-convert-python` — local Vega-Lite rendering for `/diagram vegalite`;
- `regex` + `tiktoken` — normal minBPE package imports.

The production AstrBot Python 3.12 environment was validated with Typst 0.15.0, resvg_py 0.5.0, vl-convert-python 1.9.0.post1, NetworkX 3.6.1, pydot 4.0.1, Schemdraw 0.23, python-control 0.10.2, Dans_Diffraction 3.4.0, Matplotlib 3.11.1 and SciPy 1.18.1. Plugin requirements use compatible ranges except where an implementation detail is intentionally tied to a tested version.

## External services

- `/diagram mermaid` sends source to `mermaid.ink`; the caption/help makes this explicit.
- `/run` uses the Runoob remote compiler; user code is never executed on the Doge host.
- MCPDict is not cloned. `/lang han` calls the Yindian Web backend and only keeps light in-memory caches.

## Audited implementation references only

These repositories were inspected under `/root/.cache/doge-v5` and are not runtime dependencies or copied wholesale:

- `gboeing/pynamical` — MIT, bifurcation/chaotic-map product reference;
- `lantunes/cellpylib` — Apache-2.0, cellular-automata reference;
- `alvinng4/grav_sim` — MIT, N-body reference;
- `samm00/penrose` — MIT, compact Penrose subdivision reference;
- `roberto-aldera/modular-multiplication-circles` — MIT, modular-circle reference;
- `wigging/gray-scott` and `fura2/L-system` were conceptual references only because an unambiguous top-level license was not found in the cached checkout; Doge implementations follow the published mathematical rules rather than copied source.

## Dependency principle

A normal dependency is not removed merely to reduce package count. Reimplementation is justified only when it materially improves safety, portability or simplicity. The RRPL parser is the main intentional exception: its small core was ported from JavaScript to Python to remove hardcoded Node/path deployment failures while preserving the original syntax and renderer behavior.
