"""Szukanie śladów wysłanych aplikacji w historii przeglądarek (tylko odczyt kopii plików)."""
import glob
import os
import platform
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

# katalogi danych przeglądarek względem: Windows %LOCALAPPDATA% / macOS Application Support / Linux ~/.config
CHROMIUM_DIRS = {
    "brave": ("BraveSoftware/Brave-Browser/User Data", "BraveSoftware/Brave-Browser", "BraveSoftware/Brave-Browser"),
    "chrome": ("Google/Chrome/User Data", "Google/Chrome", "google-chrome"),
    "edge": ("Microsoft/Edge/User Data", "Microsoft Edge", "microsoft-edge"),
    "chromium": ("Chromium/User Data", "Chromium", "chromium"),
    "vivaldi": ("Vivaldi/User Data", "Vivaldi", "vivaldi"),
    # Opera trzyma profil w Roaming, a nie w Local
    "opera": ("../Roaming/Opera Software/Opera Stable", "com.operasoftware.Opera", "opera"),
}
LOOKBACK_DAYS = 365
VIEWED_DAYS = 60
CLUSTER_GAP = timedelta(minutes=20)
CONTEXT_WINDOW = timedelta(minutes=60)

# strona podziękowania po wysłaniu formularza — najmocniejszy ślad
SENT = re.compile(r"thank-?you|thankyou|podziekowanie|dziekujemy|application_timestamp|/applied", re.I)
# otwarty formularz aplikacyjny
FORM = re.compile(
    r"/aplikuj/|/aplikowanie/|easy-apply|/apply\b|/apply/|/public/form/|RecruitmentForm|form\.erecruiter\.pl/form/"
    r"|recruitee\.com/o/.+/c/new|jobs\.lever\.co/.+/apply|greenhouse\.io/.+application|teamtailor.+/applications",
    re.I,
)
# strona pojedynczej oferty (kontekst: jakie stanowisko i firma)
OFFER = re.compile(
    r"justjoin\.it/job-offer/|pracuj\.pl/praca/.+,oferta,\d+|linkedin\.com/jobs/view/\d+|currentJobId=\d+"
    r"|nofluffjobs\.com/(pl/)?job/|rocketjobs\.pl/oferta-pracy/",
    re.I,
)
NOISE = re.compile(r"linkedin\.com/safety/go|CancelCreateAccount|CandidateAccount/Index", re.I)

_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
_UNIX = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _to_dt(chrome_us: int) -> datetime:
    return _EPOCH + timedelta(microseconds=chrome_us)


def _to_chrome(dt: datetime) -> int:
    return int((dt - _EPOCH).total_seconds() * 1_000_000)


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _home_dirs() -> list[tuple[str, Path]]:
    """(system, katalog domowy) — pod WSL także katalogi użytkowników Windows."""
    home = Path.home()
    system = platform.system()
    dirs = [(system, home)]
    if system == "Linux" and "microsoft" in platform.release().lower():
        dirs += [("Windows", Path(p)) for p in glob.glob("/mnt/c/Users/*") if os.access(Path(p, "AppData"), os.R_OK)]
    return dirs


def _browser_roots(browsers: list[str], extra_paths: list[str]) -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    for system, home in _home_dirs():
        for name in browsers:
            if name == "firefox":
                base = {
                    "Windows": home / "AppData/Roaming/Mozilla/Firefox/Profiles",
                    "Darwin": home / "Library/Application Support/Firefox/Profiles",
                }.get(system, home / ".mozilla/firefox")
                roots.append((name, base))
            elif name in CHROMIUM_DIRS:
                win, mac, linux = CHROMIUM_DIRS[name]
                base = {
                    "Windows": home / "AppData/Local" / win,
                    "Darwin": home / "Library/Application Support" / mac,
                }.get(system, home / ".config" / linux)
                roots.append((name, base))
    roots += [("własna ścieżka", Path(p)) for p in extra_paths]
    return roots


def history_files(browsers: list[str], extra_paths: list[str] = ()) -> list[tuple[str, Path]]:
    """Pliki historii wszystkich profili: (przeglądarka, ścieżka do History albo places.sqlite)."""
    found: list[tuple[str, Path]] = []
    for name, root in _browser_roots(browsers, list(extra_paths)):
        try:
            root = root.resolve()
            if not root.is_dir():
                continue
            subdirs = [p for p in root.iterdir() if p.is_dir()]
            candidates = [d / f for d in [root, *subdirs] for f in ("History", "places.sqlite")]
            found += [(name, c) for c in candidates if c.is_file()]
        except OSError:
            continue  # cudzy profil systemowy albo brak uprawnień
    unique = {str(p): (n, p) for n, p in found}
    return sorted(unique.values(), key=lambda x: str(x[1]))


def parse_offer_title(url: str, title: str) -> tuple[str, str]:
    """(stanowisko, firma) z tytułu strony oferty; puste pola, gdy nie da się ustalić."""
    title = (title or "").strip()
    if "linkedin.com" in url and title.count(" | ") >= 2:
        parts = title.split(" | ")
        return parts[0], parts[1]
    if "justjoin.it" in url and " - " in title:
        pos, comp = title.rsplit(" - ", 1)
        return pos, comp
    if "pracuj.pl" in url:
        m = re.search(r"/(?:praca|aplikuj)/([^,?]+),oferta", url)
        slug = unquote(m.group(1)).replace("-", " ") if m else ""
        clean = re.sub(r"\s*[|–-]\s*Pracuj\.pl.*$", "", title, flags=re.I)
        if ", " in clean and "Aplikuj" not in clean:
            pos, comp = clean.split(", ", 1)
            return re.sub(r"^Oferta pracy\s+", "", pos), comp.split(", ")[0]
        return slug, ""
    if title.startswith("Formularz aplikacyjny - "):
        return title.removeprefix("Formularz aplikacyjny - "), ""
    return title, ""


def _visits(path: Path, since: datetime) -> list[tuple[datetime, str, str]]:
    # przeglądarka trzyma plik otwarty — czytamy kopię, oryginału nie dotykamy
    firefox = path.name == "places.sqlite"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / path.name
        shutil.copyfile(path, copy)
        conn = sqlite3.connect(copy)
        try:
            if firefox:
                rows = conn.execute(
                    "select v.visit_date, p.url, coalesce(p.title, '') from moz_historyvisits v "
                    "join moz_places p on p.id = v.place_id where v.visit_date > ? order by v.visit_date",
                    (int((since - _UNIX).total_seconds() * 1_000_000),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "select v.visit_time, u.url, coalesce(u.title, '') from visits v join urls u on u.id = v.url "
                    "where v.visit_time > ? order by v.visit_time",
                    (_to_chrome(since),),
                ).fetchall()
        except sqlite3.DatabaseError:
            return []  # plik innego formatu albo uszkodzony — pomijamy profil
        finally:
            conn.close()
    if firefox:
        return [(_UNIX + timedelta(microseconds=t), url, title) for t, url, title in rows]
    return [(_to_dt(t), url, title) for t, url, title in rows]


def find_candidates(visits: list[tuple[datetime, str, str]], now: datetime | None = None) -> list[dict]:
    """Grupuje wizyty w prawdopodobne aplikacje oraz listę obejrzanych ofert bez śladu wysyłki."""
    now = now or datetime.now(timezone.utc)
    signals = [v for v in visits if not NOISE.search(v[1]) and (SENT.search(v[1]) or FORM.search(v[1]))]
    offers = [v for v in visits if OFFER.search(v[1]) and not FORM.search(v[1])]

    clusters: list[list[tuple[datetime, str, str]]] = []
    for v in signals:
        if clusters and v[0] - clusters[-1][-1][0] <= CLUSTER_GAP:
            clusters[-1].append(v)
        else:
            clusters.append([v])

    result: list[dict] = []
    used_offer_urls: set[str] = set()
    by_host: dict[str, dict] = {}
    for group in clusters:
        start, end = group[0][0], group[-1][0]
        sent = any(SENT.search(u) for _, u, _ in group)
        forms = [g for g in group if FORM.search(g[1]) and not SENT.search(g[1])]
        context = [o for o in offers if start - CONTEXT_WINDOW <= o[0] <= end]
        offer = context[-1] if context else None
        if not forms:
            # samo podziękowanie: dopinamy do wcześniejszego formularza z tej samej domeny (np. Traffit po kilku dniach)
            earlier = by_host.get(_host(group[0][1]))
            if earlier:
                earlier["kind"] = "wyslana"
                earlier["date"] = end.astimezone().date().isoformat()
                earlier["evidence"] = (earlier["evidence"] + [u for _, u, _ in group])[:6]
                continue
            if not offer:
                continue  # "dziękujemy" bez formularza i oferty to zwykle nie rekrutacja (wpłaty, newslettery)
        form = forms[0] if forms else group[0]
        title, company = parse_offer_title(offer[1], offer[2]) if offer else ("", "")
        if not title:
            title, company2 = parse_offer_title(form[1], form[2])
            company = company or company2
        if offer:
            used_offer_urls.add(offer[1])
        item = {
            "key": form[1],
            "kind": "wyslana" if sent else "formularz",
            "date": end.astimezone().date().isoformat(),
            "title": title,
            "company": company,
            "url": offer[1] if offer else form[1],
            "evidence": [u for _, u, _ in group][:6],
        }
        for _, u, _ in forms:
            by_host[_host(u)] = item
        result.append(item)

    seen: dict[str, tuple[datetime, str, str]] = {}
    for o in offers:
        if o[0] >= now - timedelta(days=VIEWED_DAYS) and o[1] not in used_offer_urls:
            seen[o[1].split("?")[0]] = o
    for url, (dt, full, page_title) in seen.items():
        title, company = parse_offer_title(full, page_title)
        result.append(
            {
                "key": url,
                "kind": "obejrzana",
                "date": dt.astimezone().date().isoformat(),
                "title": title,
                "company": company,
                "url": url,
                "evidence": [],
            }
        )
    order = {"wyslana": 0, "formularz": 1, "obejrzana": 2}
    # ta sama oferta w kilku podejściach: zostaje najmocniejszy ślad
    best: dict[tuple[str, str], dict] = {}
    for c in result:
        k = (re.sub(r"\W+", "", c["company"].lower()), re.sub(r"\W+", "", c["title"].lower()))
        if not k[0]:
            k = (c["key"], "")
        cur = best.get(k)
        if cur is None or (order[c["kind"]], cur["date"]) < (order[cur["kind"]], c["date"]):
            best[k] = c
    result = list(best.values())
    result.sort(key=lambda c: c["date"], reverse=True)
    result.sort(key=lambda c: order[c["kind"]])
    return result


def scan(files: list[tuple[str, Path]]) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    visits: list[tuple[datetime, str, str]] = []
    for _, path in files:
        visits.extend(_visits(path, since))
    visits.sort(key=lambda v: v[0])
    return find_candidates(visits)
