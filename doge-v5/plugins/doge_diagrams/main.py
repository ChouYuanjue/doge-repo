from __future__ import annotations

from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.diagrams import DiagramError, FORMATS, render_diagram
from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.help_service import format_cli_error

HELP = (
    "Doge Diagrams /diagram\n"
    "  /diagram graphviz <DOT>        本地 Graphviz\n"
    "  /diagram mermaid <source>      Mermaid（mermaid.ink 公共渲染）\n"
    "  /diagram vegalite <JSON>       本地 Vega-Lite / vl-convert\n"
    "  /diagram formats               查看稳定后端\n\n"
    "示例：/diagram graphviz digraph G { A -> B; B -> C }\n"
    "示例：/diagram mermaid flowchart LR; A-->B\n"
    "Vega-Lite 只允许 inline values，不抓取 data.url。"
)


@register("doge_diagrams", "runnel", "结构图与数据可视化：Graphviz / Mermaid / Vega-Lite", "5.4.0")
class DogeDiagrams(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("doge_diagrams")

    @filter.command("diagram")
    async def diagram(self, event: AstrMessageEvent):
        path: Path | None = None
        try:
            payload = command_payload(event.message_str, "diagram")
            if not payload.strip() or payload.strip().lower() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return
            parts = split_head(payload, 1)
            kind = parts[0].lower()
            source = parts[1] if len(parts) > 1 else ""
            if kind == "formats":
                yield text_result(event, "稳定后端：" + ", ".join(FORMATS) + "\nGraphviz/Vega-Lite 本地；Mermaid 使用 mermaid.ink。", markdown=False)
                return
            path, caption = await render_diagram(self.data_dir, kind, source)
            yield image_result(event, path, caption)
        except DiagramError as exc:
            yield text_result(event, format_cli_error('diagram', exc), markdown=False)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
