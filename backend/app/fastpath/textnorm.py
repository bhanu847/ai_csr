"""Text normalisation shared by training and prediction.

Speech-to-text output is messy: random capitals, punctuation, numbers like member/claim IDs.
We make every sentence look the same before the model sees it.
"""

from __future__ import annotations

import re
import unicodedata

_SPACE_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"\d+")


def _strip_punct(text: str) -> str:
    # Replace punctuation (P*) and symbols (S*) with spaces. Done by Unicode category so that
    # Devanagari vowel signs (category M*) are kept and Hindi words stay intact.
    return "".join(" " if unicodedata.category(ch)[0] in "PS" else ch for ch in text)


def normalize(text: str) -> str:
    """lower-case, drop punctuation, collapse spaces, and turn every number into '0'."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("'", "'").replace("'", "")  # "don't" -> "dont"
    text = _strip_punct(text)
    text = _NUM_RE.sub(" 0 ", text)  # member MEM10234 / MEM10235 look the same to the model
    return _SPACE_RE.sub(" ", text).strip()
