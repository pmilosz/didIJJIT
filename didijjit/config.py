"""Ustawienia z config.toml (albo domyślne z config.example.toml)."""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("DIDIJJIT_CONFIG", ROOT / "config.toml"))
EXAMPLE_PATH = ROOT / "config.example.toml"


@dataclass
class Config:
    categories: list[str] = field(default_factory=lambda: ["ai", "php", "python"])
    cities: list[str] = field(default_factory=lambda: ["trojmiasto"])
    radius_km: int = 0
    remote: bool = True
    only_poland: bool = True
    experience: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    browsers: list[str] = field(default_factory=lambda: ["brave", "chrome", "edge", "chromium", "opera", "vivaldi", "firefox"])
    extra_paths: list[str] = field(default_factory=list)
    port: int = 8765
    source: str = "domyślne"


def load(path: Path | None = None) -> Config:
    path = path or (CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
    if not path.exists():
        return Config()
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    jj, flt, hist, srv = (raw.get(k, {}) for k in ("justjoin", "filters", "history", "server"))
    merged = {**jj, **flt, **hist, **srv}
    known = {k: v for k, v in merged.items() if k in Config.__dataclass_fields__}
    return Config(**known, source=str(path.name))


BIG_CITIES = [
    "warszawa", "krakow", "wroclaw", "trojmiasto", "poznan", "lodz", "slask", "lublin", "rzeszow", "szczecin",
    "bydgoszcz", "torun", "bialystok", "olsztyn", "kielce", "opole", "gdansk", "gdynia", "katowice",
]
EXPERIENCE = {"junior": "Junior", "mid": "Mid", "senior": "Senior", "c_level": "C-level"}


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toggle_list(items: dict[str, str], chosen: list[str], extra_comment: dict[str, str] | None = None) -> str:
    """Lista TOML z każdą możliwą pozycją w osobnej linii; niewybrane są zakomentowane."""
    lines = []
    for slug, label in items.items():
        if extra_comment and slug in extra_comment:
            lines.append(f"  # {extra_comment[slug]}")
        item = f'"{slug}",'
        lines.append(f"  {item:<24}# {label}" if slug in chosen else f"  # {item:<22}# {label}")
    return "\n".join(lines)


def render(cfg: Config) -> str:
    """Pełny, skomentowany config.toml — ten sam układ przy zapisie z przeglądarki i w config.example.toml."""
    from .places import CATEGORIES, CITIES

    cities = {k: CITIES[k][0] + (" (aglomeracja)" if k in ("trojmiasto", "slask") else "") for k in BIG_CITIES}
    first_small = next(k for k in CITIES if k not in BIG_CITIES)
    cities |= {k: v[0] for k, v in CITIES.items() if k not in BIG_CITIES}
    lst = lambda xs: "[" + ", ".join(_q(x) for x in xs) + "]"
    b = lambda v: "true" if v else "false"
    return f'''# didIJJIT — ustawienia. Program przy pierwszym starcie kopiuje ten plik jako config.toml.
# Najprościej zmieniać je w programie: zakładka „Ustawienia”. Można też edytować ten plik ręcznie —
# wtedy kliknij „Odśwież oferty” (port zmienia się dopiero po ponownym uruchomieniu programu).
#
# JAK WYBIERAĆ: w listach poniżej usuń „#” przed pozycją, żeby ją włączyć,
# albo dopisz „#” na początku, żeby wyłączyć. Przecinki zostaw, jak są.

[justjoin]
# Technologie / kategorie justjoin.it (trzeba wybrać co najmniej jedną).
categories = [
{_toggle_list(CATEGORIES, cfg.categories)}
]

# Miasta: oferty stacjonarne i hybrydowe z tych miejsc. Pusta lista = tylko praca zdalna (jeśli remote = true).
cities = [
{_toggle_list(cities, cfg.cities, {first_small: "mniejsze miasta:"})}
]

# Promień w km wokół wybranych miast, np. 30 = także Pruszcz, Rumia czy Wejherowo dla Trójmiasta.
# 0 = tylko oferty przypisane do samych miast. Promień łapie też oferty z nazwą miasta wpisaną
# bez polskich znaków (np. „Gdansk”), które justjoin.it pomija przy wyszukiwaniu po mieście — warto ustawić choćby 10.
# Przy promieniu odświeżanie trwa dłużej, bo program pobiera oferty z całej Polski i sam liczy odległość.
radius_km = {int(cfg.radius_km)}

# Dołącz oferty w pełni zdalne z całego kraju (true = tak, false = nie).
remote = {b(cfg.remote)}

# Pomijaj oferty, których żadna lokalizacja nie leży w Polsce.
only_poland = {b(cfg.only_poland)}

# Poziom doświadczenia. Pusta lista = wszystkie.
experience = [
{_toggle_list(EXPERIENCE, cfg.experience)}
]

[filters]
# Stanowisko musi zawierać przynajmniej jedno z tych słów (wielkość liter bez znaczenia). Pusta lista = wszystkie.
# Przykład: include_keywords = ["backend", "developer", "engineer"]
include_keywords = {lst(cfg.include_keywords)}

# Pomijaj oferty, których stanowisko zawiera któreś z tych słów.
# Przykład: exclude_keywords = ["intern", "staż", "lead"]
exclude_keywords = {lst(cfg.exclude_keywords)}

# Pomijaj firmy (porównanie bez „sp. z o.o.”, „Polska” itp.).
# Przykład: exclude_companies = ["Firma A", "Firma B"]
exclude_companies = {lst(cfg.exclude_companies)}

[history]
# Przeglądarki przeszukiwane przy imporcie historii: brave, chrome, edge, chromium, opera, vivaldi, firefox.
browsers = {lst(cfg.browsers)}

# Dodatkowe katalogi z danymi przeglądarki, jeśli program sam ich nie znajdzie
# (np. "C:/Users/Ja/AppData/Local/BraveSoftware/Brave-Browser/User Data").
extra_paths = {lst(cfg.extra_paths)}

[server]
port = {int(cfg.port)}
'''


def save(cfg: Config, path: Path | None = None) -> None:
    (path or CONFIG_PATH).write_text(render(cfg), encoding="utf-8")
