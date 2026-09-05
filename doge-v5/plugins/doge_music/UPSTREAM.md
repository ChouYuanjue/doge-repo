# Community reference

The interaction and direct NetEase search route were researched from the AstrBot marketplace plugin `Mnbqq/astrbot_plugin_m`:

- https://github.com/Mnbqq/astrbot_plugin_m

That repository did not expose a LICENSE file when this integration was made, so Doge does **not** vendor or copy its source code. Doge independently implements only the small public-interface pattern needed here: NetEase search plus AstrBot/OneBot native `Music(type=163, id=...)` cards.

No LLM intent recognition, hot comments, lyric images, audio transcoding, third-party playback API, or whole-song download is used by `doge_music`.
