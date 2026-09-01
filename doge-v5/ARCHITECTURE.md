# Doge v5 architecture

## Runtime

Production on `alibaba-server-10` uses **AstrBot 4.27.4 + uv-managed Python 3.12**. One AstrBot instance serves both QQ transports:

- QQ Official: AstrBot native QQ Official WebSocket adapter;
- NapCat: rootless Linux QQ + NapCat Shell, OneBot v11 reverse WebSocket to `127.0.0.1:6199`;
- AstrBot Dashboard stays on `127.0.0.1:6185`; NapCat WebUI stays on `127.0.0.1:6099`.

No Docker image is required for the production path and Doge itself opens no public port.

## Plugin rule

A plugin is a **coherent capability that can disappear as a whole**. Commands, state, Agent tools and optional dependencies must share the same lifecycle. `doge_shared` is a library only and intentionally has no `main.py`.

Current classes:

- core: runtime/Agent foundation only;
- formal domains: math, typeset, playground, engineering, papers, bio, chem, materials, astro, clinical, games, alchemy, arena, linguistics, code, lookup, diagrams, AI and CS;
- misc: useful small utilities that do not justify an independent domain;
- legacy: optional historical museum for obsolete/offline interfaces;
- planned: architectural destinations only, never materialized until implemented and tested.

`plugin_manifest.json` is deployment truth. `feature_catalog.json` and `legacy_coverage.json` are historical audit truth.

## Agent harness

Doge uses AstrBot's native Agent Runner and `FunctionTool`; no LangChain/LangGraph layer is added. A user command and its Agent Tool call the same underlying service. Tool implementations may live in `doge_shared`, but `register_domain_tools()` rebinds `handler_module_path` to the real domain plugin so disabling a plugin also removes its tools.

Only capabilities that are actually useful to an Agent receive tools. Stateful games, protocol actions and trivial codecs are not added merely because a command exists.

## Raw command parsing

AstrBot command binding splits on spaces. Doge therefore parses `event.message_str` for code, formulas, Markdown, diagram DSLs and natural-language queries:

- remove only the first command token;
- preserve the remaining bytes/newlines;
- use bounded prefix splitting only where a structured subcommand is needed;
- let AstrBot bind arguments only for genuinely atomic parameters.

The canonical implementation is `plugins/doge_shared/raw_command.py`.

## Presentation

Business logic returns semantic results. `doge_shared.presentation` adapts them to platform capabilities:

- QQ Official: Markdown for text, native media/file upload; no reliance on outgoing `At`/`Reply` components that the current adapter drops;
- NapCat/OneBot: real `At`, images/files and native `Nodes` merged forwards for long results.

## Historical containment

Every v2/v3/v4 user-facing capability must map to formal/core/misc/legacy. Pure EPK state/plumbing may map to `internal-drop`. `tests/test_legacy_coverage.py` enforces zero unmapped historical entries.

Legacy does not pretend a dead API still works: it keeps the old command name, original intent and a short migration/offline/retired explanation.

## Security boundaries

- `/run` uses the existing remote Runoob execution service; arbitrary group code is never executed on the Doge host.
- Graphviz local rendering blocks file-image attributes and runs with time/CPU/address-space/file-size limits.
- Vega-Lite accepts inline data only; `data.url` is rejected.
- Mermaid currently uses mermaid.ink and explicitly tells users the source leaves the server.
- OneBot self-ban only operates on the sender and is never an Agent Tool.
- credentials come from AstrBot config/environment, never the repository.
