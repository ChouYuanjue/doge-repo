# Vendored GetPx subset

Source: https://github.com/shitianyaa/astrbot_plugin_get_px
Upstream revision: `63a0dd23fcc5197cf010630f89013dfb05992d41`
License: MIT; see `LICENSE` in this directory.

Only the Lolicon metadata client and image downloader are vendored. Doge does not import the upstream check-in, coin, shop, ranking, birthday, or other product features. The vendored Python files are kept byte-for-byte unchanged; Doge-specific policy and command behavior live in `doge_pixiv/service.py` and `doge_pixiv/main.py`.
