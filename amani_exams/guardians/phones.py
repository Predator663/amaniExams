import re


def normalize_phone(raw):
    """Tanzanian mobile numbers: 0712 345 678, 712345678, 255712345678 and +255 712 345 678 all become +255712345678."""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)  # Excel turns 712345678 into 712345678.0
    s = re.sub(r"[^\d+]", "", str(raw or ""))
    if s.startswith("+"):
        s = s[1:]
    elif s.startswith("00"):
        s = s[2:]
    if s.startswith("255"):
        rest = s[3:]
    elif s.startswith("0"):
        rest = s[1:]
    else:
        rest = s
    return "+255" + rest if len(rest) == 9 and rest[0] in "67" else None


def mask(phone):
    p = phone or ""
    return f"+255 {p[4]}•• ••• {p[-3:]}" if len(p) == 13 else "•••"
