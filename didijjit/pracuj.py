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


# kategorie justjoin.it rozpoznawane po słowach (kolejność ma znaczenie: pierwsza pasująca wygrywa,
# np. „Fullstack Developer (PHP / React)” → php, „Java Developer” ≠ „JavaScript”)
_CATEGORY_RULES = [(cat, re.compile(rx, re.IGNORECASE)) for cat, rx in [
    ("php", r"\bphp\b|laravel|symfony|wordpress|magento|drupal|joomla|prestashop|\byii\b"),
    ("python", r"python|django|flask|fastapi|pandas"),
    ("ai", r"\bai\b|\bml\b|\bllm|machine learning|uczeni[ea] maszynow|sztuczn\w* inteligencj|genai|data scien|deep learning|\bnlp\b|computer vision"),
    ("net", r"\.net\b|\bc#|\bdotnet|asp\.net|blazor"),
    ("java", r"\bjava\b(?!\s*script)|kotlin|spring\b"),
    ("javascript", r"javascript|typescript|\breact\b(?!\s*native)|angular|\bvue|node\.?js|front[- ]?end|next\.?js"),
    ("mobile", r"android|\bios\b|flutter|react native|swift\b|mobile|mobiln"),
    ("go", r"golang|\bgo\b(?= developer| engineer| programista)"),
    ("ruby", r"\bruby|\brails\b"),
    ("scala", r"\bscala\b"),
    ("c", r"c\+\+|\bembedded|\bc\b(?= developer| programista| engineer)|wbudowan"),
    ("devops", r"devops|\bsre\b|cloud|chmur|kubernetes|\baws\b|azure|\bgcp\b|platform engineer"),
    ("security", r"security|bezpiecze[nń]st|cyber|pentest|\bsoc\b|\bsiem\b"),
    ("testing", r"\bqa\b|tester|test(?:ów|ow|ing|owanie|er)|automatyzacj\w* test"),
    ("data", r"data engineer|big data|\betl\b|hurtowni|data warehouse|databricks|\bspark\b|in[żz]ynier danych"),
    ("analytics", r"anali(?:tyk|tic|st)|\bbi\b|business intelligence|power ?bi|tableau"),
    ("erp", r"\bsap\b|\berp\b|\bcrm\b|dynamics|salesforce|\babap\b"),
    ("ux", r"\bux\b|\bui\b|designer|projektant"),
    ("game", r"gamedev|game developer|unity|unreal|\bgier\b|\bgry\b"),
    ("pm", r"project manager|product (?:owner|manager)|scrum master|kierownik projekt|\bpmo?\b|delivery manager"),
    ("architecture", r"archite(?:kt|ct)"),
    ("admin", r"administrator|sysadmin|admin(?:istracj)|\bnetwork|sieci"),
    ("support", r"helpdesk|help desk|service desk|support|wsparci|serwisant"),
    ("html", r"\bhtml|\bcss\b|webmaster"),
]]


def _match_category(text: str) -> str:
    return next((cat for cat, rx in _CATEGORY_RULES if rx.search(text or "")), "")


def search_keywords(url: str) -> str:
    """Słowa kluczowe wyszukiwania (parametr kw), np. „php”."""
    parts = _search_parts(url)
    return " ".join(v for k, v in parts[1] if k == "kw") if parts else ""


def category(title: str, search_url: str = "") -> str:
    """Kategoria justjoin.it dla oferty z pracuj.pl: najpierw ze słów zapisanego wyszukiwania (lista „php” → PHP),
    potem z nazwy stanowiska, a gdy nic nie pasuje — „Inne”."""
    return _match_category(search_keywords(search_url)) or _match_category(title) or "other"


def allowed(title: str, company: str, cfg: Config) -> bool:
    """Z ustawień programu stosujemy tylko wykluczenia — resztę filtrów ma samo zapisane wyszukiwanie."""
    t = title.lower()
    if any(k.lower() in t for k in cfg.exclude_keywords):
        return False
    return company_key(company) not in {company_key(c) for c in cfg.exclude_companies}
