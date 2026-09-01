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
