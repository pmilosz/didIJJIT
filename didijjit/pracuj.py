"""pracuj.pl: adresy ofert i zapisanych wyszukiwań.

Program nie łączy się z pracuj.pl. Oferty i aplikacje przysyła wtyczka ze stron, które użytkownik sam otwiera
w przeglądarce (pracuj.pl chroni strony przed automatycznym pobieraniem).
"""
import re
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from .config import Config
from .db import company_key

_OFFER = re.compile(r"^https?://([a-z0-9-]+\.)*pracuj\.pl/.*,oferta,(\d+)", re.IGNORECASE)
_HOST = re.compile(r"^([a-z0-9-]+\.)*pracuj\.pl$", re.IGNORECASE)
# parametry, które nie zmieniają wyników wyszukiwania (strona wyników, śledzenie)
_SKIP_PARAMS = {"pn", "page", "rop", "searchid", "s", "ref", "sc", "sug"}


def offer_id(url: str) -> str | None:
    m = _OFFER.match((url or "").strip())
    return m.group(2) if m else None


def guid(pid: str) -> str:
    return f"pracuj:{pid}"


def clean_url(url: str) -> str:
    """Adres oferty bez parametrów i kotwicy."""
    return (url or "").strip().split("?")[0].split("#")[0]


def _search_parts(url: str) -> tuple[str, list[tuple[str, str]]] | None:
    """(host, posortowane filtry) wyszukiwania. Filtry z ścieżki („/praca/php;kw/gdynia;wp”) i z parametrów
    („?kw=php&wp=Gdynia”) dają to samo — pracuj.pl używa obu zapisów."""
    try:
        u = urlsplit((url or "").strip())
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not _HOST.match(u.hostname or "") or offer_id(url):
        return None
    segs = [unquote(x) for x in u.path.split("/") if x]
    if not segs or segs[0].lower() != "praca":
        return None
    raw = []
    for seg in segs[1:]:
        if ";" not in seg:
            continue
        val, key = seg.rsplit(";", 1)
        # kategoria w ścieżce: „it - rozwój oprogramowania;cc,5016” → cc=5016
        if "," in key:
            key, val = key.split(",", 1)
        raw.append((key, val))
    raw += parse_qsl(u.query, keep_blank_values=False)
    # wiele wartości bywa zapisanych jako „wm=home-office,hybrid” albo „wm=home-office&wm=hybrid”
    params = sorted({(k.lower(), v.strip().lower()) for k, vals in raw for v in vals.split(",")
                     if k.lower() not in _SKIP_PARAMS and not k.lower().startswith("utm_") and v.strip()})
    if not params:  # sama lista wszystkich ofert to nie wyszukiwanie
        return None
    return u.hostname.lower(), params


def search_key(url: str) -> str:
    """Znormalizowany adres wyszukiwania (do zapisu i otwierania). Pusty, jeśli to nie wyszukiwanie."""
    parts = _search_parts(url)
    return f"https://{parts[0]}/praca?{urlencode(parts[1])}" if parts else ""


def same_search(a: str, b: str) -> bool:
    """Te same filtry, niezależnie od serwisu (www / it / inzynieria.pracuj.pl) i zapisu adresu."""
    pa, pb = _search_parts(a), _search_parts(b)
    return bool(pa and pb) and pa[1] == pb[1]


def allowed(title: str, company: str, cfg: Config) -> bool:
    """Z ustawień programu stosujemy tylko wykluczenia — resztę filtrów ma samo zapisane wyszukiwanie."""
    t = title.lower()
    if any(k.lower() in t for k in cfg.exclude_keywords):
        return False
    return company_key(company) not in {company_key(c) for c in cfg.exclude_companies}
