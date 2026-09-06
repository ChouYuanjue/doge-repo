# Doge Emoji / Sticker Backend

This directory is maintained directly by the Doge repository. It is derived from `nagatoquin33/astrbot_plugin_stealer` at baseline commit `f5f51834bb0b9bb01811303c542604f805e0f019`. The original upstream documentation is preserved as `UPSTREAM_README.md` and `UPSTREAM_README_EN.md`; the upstream license remains intact.

The backend provides automatic image collection, VLM classification/tagging, semantic retrieval, scope management, automatic emoji/sticker sending, capacity maintenance, and the data-management WebUI.

It intentionally registers **no user commands and no LLM tools**. Doge owns the public surface:

- `/social emoji ...` for the collected QQ emoji/sticker library;
- `search_emoji`, `send_emoji`, `steal_emoji` are registered by `doge_social`;
- `/meme ...` and `doge_meme` belong exclusively to the fixed-template meme generator.

Do not reintroduce `/meme`, `search_meme`, `send_meme`, or `steal_meme` as public interfaces of this backend. Legacy internal config keys such as `steal_meme` and `meme_chance` remain only for compatibility with existing runtime data.
