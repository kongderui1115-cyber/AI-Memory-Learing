"""Validate URLs before including them in outbound learning reminders."""

from urllib.parse import urlsplit


def is_http_link(url: str) -> bool:
    if not url or any(char.isspace() or ord(char) < 32 or char == "\\" for char in url):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return bool(
        parts.scheme in {"http", "https"}
        and parts.hostname
        and parts.username is None
        and parts.password is None
        and port != 0
    )
