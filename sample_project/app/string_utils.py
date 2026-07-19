"""String helpers. Independent of pricing logic."""

import re


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def truncate(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    return text[: max(0, length - 3)] + "..."
