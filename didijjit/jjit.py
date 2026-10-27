"""Pobieranie ofert z publicznego API listy ofert justjoin.it."""
import httpx

from .config import Config
from .db import company_key

API = "https://justjoin.it/api/candidate-api/offers"
OFFER_URL = "https://justjoin.it/job-offer/{slug}"
PAGE = 100
MAX_PAGES = 20
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


def queries(cfg: Config) -> list[dict]:
    # API przyjmuje jedno miasto na zapytanie
    q = [{"city": c} for c in cfg.cities]
    if cfg.remote:
        q.append({"isRemote": "true"})
    return q


def fetch_all(cfg: Config, client: httpx.Client | None = None) -> list[dict]:
    """Zwraca wszystkie pasujące oferty ze wszystkich zapytań, bez duplikatów."""
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
