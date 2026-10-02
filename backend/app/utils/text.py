"""Text helpers: slugs, short codes, and query normalisation."""
import re
import secrets
import unicodedata

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion when read aloud at the counter


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "item"


def short_code(prefix: str, length: int = 6) -> str:
    return prefix + "-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


# Colloquial / regional words people type -> words that appear in listings.
SYNONYMS: dict[str, list[str]] = {
    "chappal": ["slipper", "sandal", "flip flop"],
    "chappals": ["slipper", "sandal"],
    "hawai": ["slipper", "flip flop"],
    "nali": ["tap", "faucet"],
    "nal": ["tap", "faucet"],
    "adapter": ["charger", "adaptor"],
    "adaptor": ["charger", "adapter"],
    "plug": ["charger", "socket"],
    "lead": ["cable"],
    "wire": ["cable"],
    "screen guard": ["tempered glass"],
    "screenguard": ["tempered glass"],
    "cover": ["case"],
    "pouch": ["case", "cover"],
    "bulb": ["led", "lamp"],
    "light": ["led", "lamp", "bulb"],
    "tubelight": ["batten", "tube light"],
    "pankha": ["fan"],
    "veshti": ["dhoti"],
    "dhothi": ["dhoti"],
    "banian": ["vest", "innerwear"],
    "baniyan": ["vest", "innerwear"],
    "chaddi": ["brief", "innerwear"],
    "kurti": ["kurta"],
    "copy": ["notebook"],
    "note book": ["notebook"],
    "pipe leak": ["teflon tape", "m-seal", "sealant"],
    "leak": ["teflon tape", "sealant", "m-seal"],
    "bike": ["motorcycle", "two wheeler"],
    "scooty": ["scooter", "two wheeler"],
    "gaadi": ["bike", "motorcycle"],
    "tyre": ["tube", "tire"],
    "tire": ["tyre"],
    "mobile": ["phone", "smartphone"],
    "cell": ["phone", "battery"],
    "jhadu": ["broom"],
    "pocha": ["mop"],
    "balti": ["bucket"],
    "soap powder": ["detergent"],
    "machhar": ["mosquito"],
    "mosquito coil": ["mosquito repellent"],
    "tape": ["measuring tape", "insulation tape", "teflon tape"],
}

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s\-./]")


def normalize_query(q: str) -> str:
    q = unicodedata.normalize("NFKC", q).lower().strip()
    q = _NON_WORD.sub(" ", q)
    # normalise common unit spellings: "1 ltr" -> "1 l", "25 watt" -> "25w"
    q = re.sub(r"(\d+)\s*(ltr|litre|liter|lt)\b", r"\1 l", q)
    q = re.sub(r"(\d+)\s*(watt|watts)\b", r"\1w", q)
    q = re.sub(r"(\d+)\s*(mtr|metre|meter)s?\b", r"\1 m", q)
    return _WS.sub(" ", q).strip()


def expand_synonyms(q: str) -> list[str]:
    """Extra terms to OR into keyword search. Never replaces the user's own words."""
    extra: list[str] = []
    for key, values in SYNONYMS.items():
        if re.search(rf"\b{re.escape(key)}\b", q):
            extra.extend(values)
    return extra


def search_tokens(words: list[str]) -> list[str]:
    """Words safe to put in a MongoDB $text search: letters and digits only, so user input can
    never be read as a phrase ("...") or a negation (-word)."""
    out: list[str] = []
    for w in words:
        out.extend(part for part in re.sub(r"[^\w]", " ", w).split() if len(part) >= 2)
    return list(dict.fromkeys(out))
