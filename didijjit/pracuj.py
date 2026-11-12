"""pracuj.pl: adresy ofert i zapisanych wyszukiwań.

Program nie łączy się z pracuj.pl. Oferty i aplikacje przysyła wtyczka ze stron, które użytkownik sam otwiera
w przeglądarce (pracuj.pl chroni strony przed automatycznym pobieraniem).
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from .config import Config
from .db import company_key

_OFFER = re.compile(r"^https?://([a-z0-9-]+\.)*pracuj\.pl/.*,oferta,(\d+)", re.IGNORECASE)
_HOST = re.compile(r"^([a-z0-9-]+\.)*pracuj\.pl$", re.IGNORECASE)
# parametry, które nie zmieniają wyników wyszukiwania (strona wyników, śledzenie)
_SKIP_PARAMS = {"pn", "page", "searchid", "s", "ref", "sc", "rd"}


def offer_id(url: str) -> str | None:
    m = _OFFER.match((url or "").strip())
    return m.group(2) if m else None


def guid(pid: str) -> str:
    return f"pracuj:{pid}"


def clean_url(url: str) -> str:
    """Adres oferty bez parametrów i kotwicy."""
    return (url or "").strip().split("?")[0].split("#")[0]


def search_key(url: str) -> str:
    """Znormalizowany adres wyszukiwania: bez numeru strony i parametrów śledzących. Pusty, jeśli to nie wyszukiwanie."""
    try:
        u = urlsplit((url or "").strip())
    except ValueError:
        return ""
    if u.scheme not in ("http", "https") or not _HOST.match(u.hostname or "") or offer_id(url):
        return ""
    path = u.path.rstrip("/") or "/"
    params = sorted((k, v) for k, v in parse_qsl(u.query, keep_blank_values=False)
                    if k.lower() not in _SKIP_PARAMS and not k.lower().startswith("utm_"))
    # sama strona główna bez filtrów to nie wyszukiwanie
    if path == "/" and not params:
        return ""
    return f"https://{u.hostname.lower()}{path}" + (f"?{urlencode(params)}" if params else "")


def allowed(title: str, company: str, cfg: Config) -> bool:
    """Z ustawień programu stosujemy tylko wykluczenia — resztę filtrów ma samo zapisane wyszukiwanie."""
    t = title.lower()
    if any(k.lower() in t for k in cfg.exclude_keywords):
        return False
    return company_key(company) not in {company_key(c) for c in cfg.exclude_companies}
