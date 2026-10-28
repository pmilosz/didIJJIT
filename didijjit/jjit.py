"""Pobieranie ofert z publicznego API listy ofert justjoin.it."""
import math

import httpx

from .config import Config
from .db import company_key
from .places import CATEGORIES, CITIES

API = "https://justjoin.it/api/candidate-api/offers"
OFFER_URL = "https://justjoin.it/job-offer/{slug}"
PAGE = 100
MAX_PAGES = 60
HEADERS = {"User-Agent": "Mozilla/5.0 (didIJJIT; prywatne narzedzie)", "Accept": "application/json"}
# prostokąt obejmujący Polskę — API nie podaje kraju, tylko współrzędne
POLAND = (49.0, 54.9, 14.1, 24.2)


def _salary(employment_types: list[dict]) -> str:
    parts = []
    for e in employment_types:
        # from/to bywają przeliczone na miesiąc — właściwa stawka jest w polach *PerUnit
        low, high = e.get("fromPerUnit") or e.get("from"), e.get("toPerUnit") or e.get("to")
        if e.get("currencySource") != "original" or low is None:
            continue
        unit = {"hour": "/h", "month": "/mies.", "day": "/dzień", "year": "/rok"}.get((e.get("unit") or "").lower(), "")
        kind = {"b2b": "B2B", "permanent": "UoP", "mandate_contract": "UZ"}.get(e.get("type"), "")
        to = f"–{high:,.0f}" if high else ""
        parts.append(f"{low:,.0f}{to} {e['currency']}{unit} {kind}".replace(",", " ").strip())
    return " · ".join(parts)


def _in_poland(raw: dict) -> bool:
    lat_min, lat_max, lon_min, lon_max = POLAND
    points = raw.get("locations") or [raw]
    return any(
        lat_min <= (p.get("latitude") or 0) <= lat_max and lon_min <= (p.get("longitude") or 0) <= lon_max
        for p in points
    )


def normalize(raw: dict) -> dict:
    return {
        "guid": raw["guid"],
        "slug": raw["slug"],
        "title": raw["title"],
        "company": raw.get("companyName") or "?",
        "city": raw.get("city") or "",
        "workplace": raw.get("workplaceType") or "",
        "experience": raw.get("experienceLevel") or "",
        "category": (raw.get("category") or {}).get("key") or "",
        "salary": _salary(raw.get("employmentTypes") or []),
        "apply_url": raw.get("applyUrl") or "",
        "published_at": raw.get("publishedAt") or "",
    }


def matches(raw: dict, cfg: Config) -> bool:
    """Filtry z config.toml, których API nie obsługuje."""
    title = (raw.get("title") or "").lower()
    if cfg.only_poland and not _in_poland(raw):
        return False
    if cfg.experience and (raw.get("experienceLevel") or "") not in cfg.experience:
        return False
    if cfg.include_keywords and not any(k.lower() in title for k in cfg.include_keywords):
        return False
    if any(k.lower() in title for k in cfg.exclude_keywords):
        return False
    excluded = {company_key(c) for c in cfg.exclude_companies}
    return company_key(raw.get("companyName") or "") not in excluded


def validate(cfg: Config) -> None:
    """Literówka w slugu dałaby po cichu zero ofert — lepiej powiedzieć wprost."""
    bad_cat = [c for c in cfg.categories if c not in CATEGORIES]
    bad_city = [c for c in cfg.cities if c not in CITIES]
    if bad_cat:
        raise ValueError(f"Nieznane kategorie w config.toml: {', '.join(bad_cat)}. Dozwolone: {', '.join(CATEGORIES)}")
    if bad_city:
        raise ValueError(f"Nieznane miasta w config.toml: {', '.join(bad_city)}. Dozwolone: {', '.join(CITIES)}")
    if not cfg.categories:
        raise ValueError("W config.toml nie wybrano żadnej kategorii")


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def near(raw: dict, cfg: Config) -> bool:
    """Czy któraś lokalizacja oferty leży w promieniu radius_km od któregoś z wybranych miast."""
    points = raw.get("locations") or [raw]
    centers = [CITIES[c][1:] for c in cfg.cities]
    return any(
        _km(p.get("latitude") or 0, p.get("longitude") or 0, lat, lon) <= cfg.radius_km
        for p in points for lat, lon in centers
    )


def queries(cfg: Config) -> list[dict]:
    if cfg.cities and cfg.radius_km > 0:
        # API nie zna promienia: bierzemy całą Polskę i liczymy odległość sami
        q = [{}]
    else:
        # API przyjmuje jedno miasto na zapytanie
        q = [{"city": c} for c in cfg.cities]
    if cfg.remote:
        q.append({"isRemote": "true"})
    return q


def fetch_all(cfg: Config, client: httpx.Client | None = None) -> list[dict]:
    """Zwraca wszystkie pasujące oferty ze wszystkich zapytań, bez duplikatów."""
    validate(cfg)
    own = client is None
    client = client or httpx.Client(timeout=30, headers=HEADERS)
    found: dict[str, dict] = {}
    try:
        for extra in queries(cfg):
            start = 0
            for _ in range(MAX_PAGES):
                params = [("categories", c) for c in cfg.categories] + list(extra.items()) + [
                    ("itemsCount", PAGE),
                    ("from", start),
                    ("orderBy", "descending"),
                    ("sortBy", "publishedAt"),
                ]
                resp = client.get(API, params=params)
                resp.raise_for_status()
                body = resp.json()
                for raw in body.get("data", []):
                    if extra == {} and not near(raw, cfg):
                        continue
                    if raw["guid"] not in found and matches(raw, cfg):
                        found[raw["guid"]] = normalize(raw)
                nxt = (body.get("meta") or {}).get("next") or {}
                if nxt.get("cursor") is None or not body.get("data"):
                    break
                start = nxt["cursor"]
    finally:
        if own:
            client.close()
    return list(found.values())
