"""
Conflict Router — maps incoming signals to a specific conflict_id.

Called by store.py before INSERT when conflict_id is None.
Uses three matching strategies (in order):
  1. Country-code in source_name  (e.g. CloudflareRadar/YE → Yemen)
  2. Keyword match in content text
  3. Lat/lon bounding box         (for satellite/FIRMS signals)

Returns conflict_id string or None (signal stays unlinked).
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger("strategos.conflict_router")

# ── Conflict definitions ─────────────────────────────────────────────────────

CONFLICTS: list[dict] = [
    {
        "id": "10000000-0000-0000-0000-000000000001",
        "name": "Russia-Ukraine War",
        "country_codes": ["UA", "RU"],
        "keywords": [
            "ukraine", "ukrainian", "russia", "russian", "kyiv", "kiev",
            "moscow", "donbas", "donbass", "crimea", "zaporizhzhia",
            "kharkiv", "kherson", "mariupol", "zelensky", "putin", "nato",
            "dnipro", "odesa", "odessa", "luhansk", "donetsk", "bakhmut",
        ],
        "bbox": [  # [min_lon, min_lat, max_lon, max_lat]
            (22.0, 44.0, 40.5, 52.5),   # Ukraine
            (27.0, 45.0, 40.5, 55.5),   # Western Russia / Black Sea region
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000002",
        "name": "Gaza Conflict",
        "country_codes": ["IL", "PS", "LB"],
        "keywords": [
            "gaza", "israel", "israeli", "hamas", "west bank", "palestine",
            "palestinian", "idf", "hezbollah", "netanyahu", "rafah",
            "tel aviv", "jerusalem", "beirut", "sinai", "suez",
        ],
        "bbox": [
            (34.2, 29.3, 35.9, 33.5),   # Israel / Gaza / West Bank
            (35.2, 33.0, 36.7, 34.5),   # Lebanon
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000003",
        "name": "Taiwan Strait Tensions",
        "country_codes": ["TW", "CN"],
        "keywords": [
            "taiwan", "taiwanese", "strait", "china", "chinese", "beijing",
            "pla", "prc", "tsai", "xi jinping", "taipei", "south china sea",
            "pla navy", "carrier group",
        ],
        "bbox": [
            (119.0, 21.0, 125.0, 27.0),  # Taiwan Strait
            (108.0, 18.0, 122.0, 26.0),  # South China Sea (north)
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000004",
        "name": "Sudan Civil War",
        "country_codes": ["SD", "SS"],
        "keywords": [
            "sudan", "sudanese", "khartoum", "darfur", "rsf", "saf",
            "rapid support forces", "juba", "south sudan", "el fasher",
            "hemeti", "burhan",
        ],
        "bbox": [
            (21.8, 3.5, 38.7, 22.2),    # Sudan
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000005",
        "name": "Iran Nuclear Program",
        "country_codes": ["IR"],
        "keywords": [
            "iran", "iranian", "tehran", "iaea", "nuclear", "uranium",
            "enrichment", "natanz", "fordow", "sanctions", "rouhani",
            "khamenei", "revolutionary guard", "irgc", "persian gulf",
        ],
        "bbox": [
            (44.0, 25.0, 63.5, 39.8),   # Iran
            (48.0, 23.0, 57.0, 27.5),   # Persian Gulf
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000006",
        "name": "Yemen/Houthi Conflict",
        "country_codes": ["YE"],
        "keywords": [
            "yemen", "yemeni", "houthi", "houthis", "sanaa", "aden",
            "red sea", "bab el-mandeb", "hodeidah", "ansarallah",
            "saudi coalition", "marib", "taiz",
        ],
        "bbox": [
            (42.5, 12.0, 53.5, 18.0),   # Yemen
            (32.0, 11.0, 43.5, 16.0),   # Red Sea / Bab el-Mandeb
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000007",
        "name": "Myanmar Civil War",
        "country_codes": ["MM"],
        "keywords": [
            "myanmar", "burma", "burmese", "naypyidaw", "yangon",
            "tatmadaw", "nug", "pdf", "arakan", "rakhine", "shan",
            "kachin", "karen", "rohingya", "min aung hlaing",
        ],
        "bbox": [
            (92.0, 9.5, 101.5, 28.5),   # Myanmar
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000008",
        "name": "South China Sea Dispute",
        "country_codes": ["PH", "VN"],
        "keywords": [
            "south china sea", "spratly", "paracel", "scarborough",
            "philippines", "philippine", "vietnam", "vietnamese",
            "second thomas shoal", "manila", "hanoi", "ayungin",
            "west philippine sea",
        ],
        "bbox": [
            (109.0, 5.0, 121.0, 22.0),  # South China Sea
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000009",
        "name": "Sahel Instability",
        "country_codes": ["ML", "NE", "BF", "TD", "MR"],
        "keywords": [
            "sahel", "mali", "malian", "niger", "burkina faso", "chad",
            "mauritania", "bamako", "niamey", "ouagadougou", "wagner",
            "jihadist", "jnim", "aqim", "islamic state sahel",
            "g5 sahel", "ecowas",
        ],
        "bbox": [
            (-17.0, 11.0, 24.0, 25.0),  # Sahel belt
        ],
    },
    {
        "id": "10000000-0000-0000-0000-000000000010",
        "name": "Venezuela Political Crisis",
        "country_codes": ["VE"],
        "keywords": [
            "venezuela", "venezuelan", "caracas", "maduro", "guaido",
            "chavismo", "pdvsa", "bolivar", "maracaibo",
        ],
        "bbox": [
            (-73.5, 0.6, -59.5, 12.5),  # Venezuela
        ],
    },
]

# ── Pre-compiled keyword lookup ───────────────────────────────────────────────

_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (c["keywords"], c["id"]) for c in CONFLICTS
]

_CC_MAP: dict[str, str] = {}
for _c in CONFLICTS:
    for _code in _c.get("country_codes", []):
        _CC_MAP[_code] = _c["id"]

_CC_PATTERN = re.compile(r"/([A-Z]{2})(?:[/_]|$)")


def _match_country_code(source_name: str) -> str | None:
    """Extract ISO-2 country code from source_name like 'CloudflareRadar/YE'."""
    m = _CC_PATTERN.search(source_name)
    if m:
        return _CC_MAP.get(m.group(1))
    return None


def _match_keywords(text: str) -> str | None:
    """First conflict whose keyword appears in lowercased text."""
    low = text.lower()
    for keywords, conflict_id in _KEYWORD_MAP:
        for kw in keywords:
            if kw in low:
                return conflict_id
    return None


def _match_bbox(lat: float | None, lon: float | None) -> str | None:
    """Match lat/lon against conflict bounding boxes (first match wins)."""
    if lat is None or lon is None:
        return None
    for c in CONFLICTS:
        for min_lon, min_lat, max_lon, max_lat in c.get("bbox", []):
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                return c["id"]
    return None


def resolve(sig: dict) -> str | None:
    """
    Return conflict_id for the given signal dict, or None.

    Priority: country-code > lat/lon bbox > keyword match.
    """
    source_name: str = sig.get("source_name", "")
    content: str = sig.get("content", "") or ""
    lat = sig.get("latitude")
    lon = sig.get("longitude")

    # 1. Country code in source_name (fastest, most precise)
    conflict_id = _match_country_code(source_name)
    if conflict_id:
        return conflict_id

    # 2. Bounding box (good for satellite / FIRMS signals)
    conflict_id = _match_bbox(lat, lon)
    if conflict_id:
        return conflict_id

    # 3. Keyword match on content + source_name
    combined = f"{source_name} {content}"
    conflict_id = _match_keywords(combined)
    return conflict_id
