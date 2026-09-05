from __future__ import annotations


def command_payload(raw: str | None, *aliases: str) -> str:
    """Remove exactly one command token and preserve the remaining payload."""
    text = (raw or "").lstrip()
    if text.startswith("/"):
        text = text[1:]
    for alias in sorted({a.lstrip("/") for a in aliases}, key=len, reverse=True):
        if text == alias:
            return ""
        if text.startswith(alias):
            tail = text[len(alias) :]
            if tail and tail[0].isspace():
                return tail.lstrip(" \t")
    raise ValueError(f"message does not start with command aliases: {aliases!r}")


def split_head(payload: str, maxsplit: int = 1) -> list[str]:
    """Split only a bounded command prefix; never flatten the whole payload."""
    if not payload.strip():
        return []
    return payload.strip().split(None, maxsplit)


def original_message_text(event) -> str:
    """Return the transport-level message before AstrBot wake-prefix rewriting.

    ``event.message_str`` may have its leading slash removed by WakingCheckStage.
    ``message_obj.message_str`` retains the original transport text and must be
    preferred for deciding whether a passive handler is allowed to run.
    """
    message_obj = getattr(event, "message_obj", None)
    return str(
        getattr(message_obj, "message_str", "")
        or getattr(event, "message_str", "")
        or ""
    )
