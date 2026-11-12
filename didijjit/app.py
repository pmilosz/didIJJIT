"""didIJJIT — lokalna lista ofert z justjoin.it i rejestr wysłanych aplikacji."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import io
import json
import os
import platform
import zipfile

from . import config, db, history, jjit, pracuj
from .places import CATEGORIES, CITIES

STATIC = Path(__file__).resolve().parent / "static"
EXTENSION = Path(__file__).resolve().parent.parent / "extension"
SORTS = {
    "najnowsze": "published_at desc",
    "kategoria": "category, published_at desc",
    "firma": "lower(company), published_at desc",
    "miasto": "city, published_at desc",
}
Status = Literal["nowa", "przejrzana", "aplikowalem", "nie_interesuje"]
VIEWS = {
    "nowe": "active = 1 and status = 'nowa'",
    "aktywne": "active = 1",
    "przejrzane": "active = 1 and status = 'przejrzana'",
    "aplikowalem": "status = 'aplikowalem'",
    "nie_interesuje": "status = 'nie_interesuje'",
    "wygasle": "active = 0",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(title="didIJJIT", lifespan=lifespan)
# wtyczka przeglądarki pyta serwer z własnego adresu chrome-extension:// albo moz-extension://
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome|moz)-extension://.*$",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _offer_for_url(conn, url: str):
    """Oferta z bazy wskazywana przez adres justjoin.it albo pracuj.pl."""
    slug = _jjit_slug(url)
    if slug:
        return conn.execute("select * from offers where slug = ? and source = 'jjit'", (slug,)).fetchone()
    pid = pracuj.offer_id(url)
    return conn.execute("select * from offers where guid = ?", (pracuj.guid(pid),)).fetchone() if pid else None


def _link_applications(conn) -> None:
    """Oznacza oferty jako 'aplikowałem', jeśli aplikacja wskazuje tę samą ofertę (adres albo firma + stanowisko)."""
    for a in conn.execute("select * from applications where offer_guid is null").fetchall():
        offer = _offer_for_url(conn, a["url"]) if a["url"] else None
        if not offer and a["title"].strip():
            tk = db.title_key(a["title"])
            offer = next((o for o in conn.execute(
                "select guid, title from offers where company_key = ? and status != 'aplikowalem' order by active desc",
                (a["company_key"],),
            ) if tk and db.title_key(o["title"]) == tk), None)
        if offer:
            conn.execute("update applications set offer_guid = ? where id = ?", (offer["guid"], a["id"]))
            conn.execute(
                "update offers set status = 'aplikowalem', status_at = ? where guid = ?",
                (a["applied_at"], offer["guid"]),
            )


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/summary")
def summary():
    with db.session() as conn:
        counts = {k: conn.execute(f"select count(*) from offers where {w}").fetchone()[0] for k, w in VIEWS.items()}
        last = conn.execute("select * from refreshes order by id desc limit 1").fetchone()
        apps = conn.execute("select count(*) from applications").fetchone()[0]
        # aktywne oferty firm, do których już wysłano CV (bez ofert, na które aplikowano)
        warnings = conn.execute(
            "select count(*) from offers where active = 1 and status != 'aplikowalem' "
            "and company_key in (select company_key from applications)"
        ).fetchone()[0]
    cfg = config.load()
    return {
        "counts": counts,
        "applications": apps,
        "warnings": warnings,
        "last_refresh": dict(last) if last else None,
        "config": {"source": cfg.source, "categories": cfg.categories, "cities": cfg.cities, "radius_km": cfg.radius_km,
                   "remote": cfg.remote},
    }


@app.post("/api/refresh")
def refresh():
    try:
        fetched = jjit.fetch_all(config.load())
    except ValueError as exc:  # błąd w config.toml
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # błąd sieci albo zmiana API po stronie justjoin.it
        raise HTTPException(502, f"Nie udało się pobrać ofert z justjoin.it: {exc}") from exc
    now = _now()
    with db.session() as conn:
        cur = conn.execute("insert into refreshes (at, fetched, added) values (?, ?, 0)", (now, len(fetched)))
        refresh_id = cur.lastrowid
        added = 0
        for o in fetched:
            exists = conn.execute("select 1 from offers where guid = ?", (o["guid"],)).fetchone()  # guid z jjit, bez prefiksu
            if exists:
                conn.execute(
                    "update offers set title=?, company=?, city=?, workplace=?, experience=?, category=?, salary=?, "
                    "apply_url=?, published_at=?, last_seen_at=?, last_seen_refresh=?, active=1 where guid=?",
                    (o["title"], o["company"], o["city"], o["workplace"], o["experience"], o["category"],
                     o["salary"], o["apply_url"], o["published_at"], now, refresh_id, o["guid"]),
                )
            else:
                added += 1
                conn.execute(
                    "insert into offers (guid, slug, title, company, company_key, city, workplace, experience, category, "
                    "salary, apply_url, published_at, first_seen_at, first_seen_refresh, last_seen_at, last_seen_refresh) "
                    "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (o["guid"], o["slug"], o["title"], o["company"], db.company_key(o["company"]), o["city"],
                     o["workplace"], o["experience"], o["category"], o["salary"], o["apply_url"], o["published_at"],
                     now, refresh_id, now, refresh_id),
                )
        # oferty, których API już nie zwraca (albo nie pasują do nowych ustawień): nietknięte usuwamy,
        # a te ze statusem lub notatką zostają jako wygasłe
        if fetched:
            conn.execute(
                "delete from offers where source = 'jjit' and last_seen_refresh is not ? and status = 'nowa' "
                "and note = '' and guid not in (select offer_guid from applications where offer_guid is not null)",
                (refresh_id,),
            )
            conn.execute("update offers set active = 0 where source = 'jjit' and last_seen_refresh is not ?", (refresh_id,))
        conn.execute("update refreshes set added = ? where id = ?", (added, refresh_id))
        _link_applications(conn)
    return {"fetched": len(fetched), "added": added}


@app.get("/api/offers")
def offers(view: str = "nowe", q: str = "", category: str = "", sort: str = "najnowsze", hide_applied: bool = False):
    if view not in VIEWS or sort not in SORTS:
        raise HTTPException(400, "Nieznany widok albo sortowanie")
    with db.session() as conn:
        last = conn.execute("select max(id) from refreshes").fetchone()[0]
        sql = f"select * from offers where {VIEWS[view]}"
        args: list = []
        if q.strip():
            sql += " and (title like ? or company like ? or city like ?)"
            args += [f"%{q.strip()}%"] * 3
        if hide_applied:
            # bez ofert firm, do których już wysłano CV (także tej samej oferty)
            sql += " and status != 'aplikowalem' and company_key not in (select company_key from applications)"
        # liczniki kategorii liczymy przed zawężeniem do jednej kategorii, żeby zakładki nie znikały
        cats = {r[0]: r[1] for r in conn.execute(f"select category, count(*) from ({sql}) group by category", args)}
        if category:
            sql += " and category = ?"
            args.append(category)
        sql += f" order by {SORTS[sort]}"
        rows = [dict(r) for r in conn.execute(sql, args)]
        history: dict[str, list[dict]] = {}
        for a in conn.execute("select * from applications order by applied_at desc"):
            history.setdefault(a["company_key"], []).append(dict(a))
    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    for r in rows:
        if r["source"] == "jjit":
            r["fresh"] = r["first_seen_refresh"] == last
            r["url"] = jjit.OFFER_URL.format(slug=r["slug"])
        else:  # pracuj.pl: oferty dochodzą przy oglądaniu wyszukiwań, nie przy odświeżeniu
            r["fresh"] = r["first_seen_at"] >= day_ago
        tk = db.title_key(r["title"])
        r["company_history"] = [
            {**a, "same_title": bool(tk) and db.title_key(a["title"]) == tk}
            for a in history.get(r["company_key"], []) if a["offer_guid"] != r["guid"]
        ]
    return {"offers": rows, "categories": cats}


class StatusIn(BaseModel):
    status: Status
    applied_at: date | None = None


@app.post("/api/offers/{guid}/status")
def set_status(guid: str, body: StatusIn):
    with db.session() as conn:
        offer = conn.execute("select * from offers where guid = ?", (guid,)).fetchone()
        if not offer:
            raise HTTPException(404, "Nie ma takiej oferty")
        when = (body.applied_at or date.today()).isoformat() if body.status == "aplikowalem" else _now()
        conn.execute("update offers set status = ?, status_at = ? where guid = ?", (body.status, when, guid))
        if body.status == "aplikowalem":
            linked = conn.execute("select id from applications where offer_guid = ?", (guid,)).fetchone()
            if linked:
                conn.execute("update applications set applied_at = ? where id = ?", (when, linked["id"]))
            else:
                conn.execute(
                    "insert into applications (company, company_key, title, url, applied_at, source, offer_guid) "
                    "values (?,?,?,?,?,?,?)",
                    (offer["company"], offer["company_key"], offer["title"],
                     offer["url"] or jjit.OFFER_URL.format(slug=offer["slug"]), when, "oferta", guid),
                )
        else:
            # cofnięcie 'aplikowałem' usuwa wpis utworzony z tej oferty
            conn.execute("delete from applications where offer_guid = ? and source = 'oferta'", (guid,))
            conn.execute("update applications set offer_guid = null where offer_guid = ?", (guid,))
    return {"ok": True}


class NoteIn(BaseModel):
    note: str


@app.post("/api/offers/{guid}/note")
def set_note(guid: str, body: NoteIn):
    with db.session() as conn:
        conn.execute("update offers set note = ? where guid = ?", (body.note.strip(), guid))
    return {"ok": True}


@app.get("/api/applications")
def applications():
    with db.session() as conn:
        return [dict(r) for r in conn.execute("select * from applications order by applied_at desc, id desc")]


class ApplicationIn(BaseModel):
    company: str
    title: str = ""
    url: str = ""
    applied_at: date
    note: str = ""
    source: Literal["reczna", "historia", "wtyczka", "pracuj"] = "reczna"
    history_key: str | None = None


def _insert_application(conn, a: ApplicationIn) -> None:
    if not a.company.strip():
        raise HTTPException(400, "Podaj nazwę firmy")
    conn.execute(
        "insert into applications (company, company_key, title, url, applied_at, source, note) values (?,?,?,?,?,?,?)",
        (a.company.strip(), db.company_key(a.company), a.title.strip(), a.url.strip(), a.applied_at.isoformat(),
         a.source, a.note.strip()),
    )
    if a.history_key:
        conn.execute("insert or ignore into history_dismissed (key) values (?)", (a.history_key,))


@app.post("/api/applications")
def add_application(body: ApplicationIn):
    with db.session() as conn:
        _insert_application(conn, body)
        _link_applications(conn)
    return {"ok": True}


@app.delete("/api/applications/{app_id}")
def delete_application(app_id: int):
    with db.session() as conn:
        a = conn.execute("select * from applications where id = ?", (app_id,)).fetchone()
        if not a:
            raise HTTPException(404, "Nie ma takiego wpisu")
        conn.execute("delete from applications where id = ?", (app_id,))
        if a["offer_guid"]:
            conn.execute("update offers set status = 'przejrzana', status_at = ? where guid = ?", (_now(), a["offer_guid"]))
    return {"ok": True}


@app.get("/api/history/candidates")
def history_candidates():
    cfg = config.load()
    files = history.history_files(cfg.browsers, cfg.extra_paths)
    if not files:
        raise HTTPException(404, "Nie znaleziono historii żadnej przeglądarki. Dopisz ścieżkę w config.toml → [history] extra_paths.")
    found = history.scan(files)
    with db.session() as conn:
        skip = {r[0] for r in conn.execute("select key from history_dismissed")}
        skip |= {r[0] for r in conn.execute("select url from applications where url != ''")}
    return {
        "browsers": sorted({name for name, _ in files}),
        "profiles": len(files),
        "items": [c for c in found if c["key"] not in skip and c["url"] not in skip],
    }


class BatchIn(BaseModel):
    items: list[ApplicationIn] = []
    dismiss: list[str] = []


@app.post("/api/history/import")
def history_import(body: BatchIn):
    with db.session() as conn:
        for item in body.items:
            _insert_application(conn, item.model_copy(update={"source": "historia"}))
        for key in body.dismiss:
            conn.execute("insert or ignore into history_dismissed (key) values (?)", (key,))
        _link_applications(conn)
    return {"imported": len(body.items), "dismissed": len(body.dismiss)}


def _jjit_slug(url: str) -> str | None:
    if "justjoin.it/job-offer/" not in url:
        return None
    return url.split("justjoin.it/job-offer/", 1)[1].split("?")[0].split("#")[0].strip("/")


@app.get("/api/lookup")
def lookup(url: str, company: str = "", title: str = ""):
    """Dla wtyczki: czy ta oferta jest w bazie i czy aplikowałeś już do tej firmy."""
    pid = pracuj.offer_id(url)
    clean = pracuj.clean_url(url) if pid else url.split("?")[0]
    with db.session() as conn:
        offer = _offer_for_url(conn, url)
        key = offer["company_key"] if offer else db.company_key(company) if company.strip() else None
        apps = [dict(a) for a in conn.execute(
            "select * from applications where company_key = ? or (url != '' and url = ?) order by applied_at desc",
            (key, clean),
        )] if key or url else []
    # ta sama oferta bywa opublikowana w kilku kategoriach pod różnymi adresami — porównujemy też stanowisko
    tk = db.title_key(offer["title"] if offer else title)
    same_title = lambda a: bool(tk) and a["company_key"] == key and db.title_key(a["title"]) == tk
    this_offer = [
        a for a in apps
        if (offer and a["offer_guid"] == offer["guid"]) or a["url"] == clean or same_title(a)
        or (pid and pracuj.offer_id(a["url"]) == pid)
    ]
    return {
        "offer": {k: offer[k] for k in ("guid", "title", "company", "status", "status_at")} if offer else None,
        "applied_here": this_offer[0] if this_offer else None,
        "company_history": [a for a in apps if a not in this_offer],
    }


class CompaniesIn(BaseModel):
    companies: list[str]


@app.post("/api/companies/applied")
def companies_applied(body: CompaniesIn):
    """Dla wtyczki na liście ofert: do których z tych firm już wysłano CV (nazwa → data ostatniej aplikacji)."""
    keys = {c: db.company_key(c) for c in body.companies[:500] if c.strip()}
    with db.session() as conn:
        last = {r[0]: r[1] for r in conn.execute("select company_key, max(applied_at) from applications group by company_key")}
    return {c: last[k] for c, k in keys.items() if k in last}


class PageApplyIn(BaseModel):
    url: str
    company: str
    title: str = ""


@app.post("/api/applied-from-page")
def applied_from_page(body: PageApplyIn):
    """Wtyczka: użytkownik potwierdził, że wysłał CV na tej stronie."""
    with db.session() as conn:
        offer = _offer_for_url(conn, body.url)
    if offer:
        return set_status(offer["guid"], StatusIn(status="aplikowalem"))
    with db.session() as conn:
        _insert_application(conn, ApplicationIn(
            company=body.company, title=body.title, url=body.url.split("?")[0].split("#")[0], applied_at=date.today(),
            source="wtyczka",
        ))
        _link_applications(conn)
    return {"ok": True}


# ===== pracuj.pl: dane przysyła wtyczka ze stron, które użytkownik sam otwiera =====

class PracujOfferIn(BaseModel):
    url: str
    title: str
    company: str
    city: str = ""
    workplace: str = ""
    experience: str = ""
    salary: str = ""
    published_at: str = ""


class PracujOffersIn(BaseModel):
    offers: list[PracujOfferIn]
    search_url: str = ""


@app.post("/api/pracuj/offers")
def pracuj_offers(body: PracujOffersIn):
    """Wtyczka: oferty z oglądanej strony zapisanego wyszukiwania pracuj.pl."""
    now = _now()
    added = 0
    cfg = config.load()
    with db.session() as conn:
        for o in body.offers[:300]:
            pid = pracuj.offer_id(o.url)
            if not pid or not o.title.strip() or not o.company.strip():
                continue
            if not pracuj.allowed(o.title, o.company, cfg):
                continue
            guid = pracuj.guid(pid)
            fields = (o.title.strip(), o.company.strip(), db.company_key(o.company), o.city, o.workplace, o.experience,
                      o.salary, o.published_at, pracuj.clean_url(o.url))
            if conn.execute("select 1 from offers where guid = ?", (guid,)).fetchone():
                conn.execute(
                    "update offers set title=?, company=?, company_key=?, city=?, workplace=?, experience=?, salary=?, "
                    "published_at=coalesce(nullif(?, ''), published_at), url=?, last_seen_at=?, active=1 where guid=?",
                    (*fields, now, guid),
                )
            else:
                added += 1
                conn.execute(
                    "insert into offers (guid, slug, title, company, company_key, city, workplace, experience, category, "
                    "salary, apply_url, published_at, url, first_seen_at, last_seen_at, source) "
                    "values (?,?,?,?,?,?,?,?,'pracuj',?,'',?,?,?,?,'pracuj')",
                    (guid, guid, *fields[:6], fields[6], fields[7] or now, fields[8], now, now),
                )
        if body.search_url:
            for s in conn.execute("select url from pracuj_searches").fetchall():
                if pracuj.same_search(s["url"], body.search_url):
                    conn.execute("update pracuj_searches set last_visit_at = ?, last_count = ? where url = ?",
                                 (now, len(body.offers), s["url"]))
        # oferty niewidziane od 30 dni: nietknięte usuwamy, pozostałe oznaczamy jako wygasłe
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
        conn.execute(
            "delete from offers where source = 'pracuj' and last_seen_at < ? and status = 'nowa' and note = '' "
            "and guid not in (select offer_guid from applications where offer_guid is not null)", (old,))
        conn.execute("update offers set active = 0 where source = 'pracuj' and last_seen_at < ?", (old,))
        _link_applications(conn)
    return {"received": len(body.offers), "added": added}


@app.get("/api/pracuj/searches")
def pracuj_searches():
    with db.session() as conn:
        return [dict(r) for r in conn.execute("select * from pracuj_searches where hidden = 0 order by added_at")]


class SearchIn(BaseModel):
    url: str
    name: str = ""


class SearchesIn(BaseModel):
    searches: list[SearchIn]
    # automatyczny import zapisanych wyszukiwań z konta pracuj.pl: usunięte w programie nie wracają,
    # a adres prowadzi do www.pracuj.pl (wszystkie kategorie, nie tylko np. inzynieria.pracuj.pl)
    auto: bool = False


@app.post("/api/pracuj/searches")
def pracuj_add_searches(body: SearchesIn):
    """Dodanie zapisanych wyszukiwań (z wtyczki albo wklejonego adresu). Zwraca liczbę nowych."""
    added = 0
    with db.session() as conn:
        for s in body.searches[:100]:
            key = pracuj.search_key(s.url)
            if key and body.auto:
                key = "https://www.pracuj.pl/" + key.split("/", 3)[3]
            if not key:
                if len(body.searches) == 1:
                    raise HTTPException(400, "To nie jest adres wyszukiwania ofert na pracuj.pl")
                continue
            same = [r for r in conn.execute("select url, hidden from pracuj_searches") if pracuj.same_search(r["url"], key)]
            if same:
                if not body.auto and same[0]["hidden"]:  # ręcznie dodane jeszcze raz — przywracamy
                    conn.execute("update pracuj_searches set hidden = 0 where url = ?", (same[0]["url"],))
                    added += 1
                continue
            conn.execute("insert into pracuj_searches (url, name, added_at) values (?,?,?)", (key, s.name.strip()[:200], _now()))
            added += 1
    return {"added": added}


@app.post("/api/pracuj/searches/delete")
def pracuj_delete_search(body: SearchIn):
    with db.session() as conn:
        # zostaje ukryte, żeby automatyczny import z pracuj.pl go nie przywracał
        conn.execute("update pracuj_searches set hidden = 1 where url = ?", (body.url,))
    return {"ok": True}


@app.get("/api/pracuj/search-known")
def pracuj_search_known(url: str):
    """Dla wtyczki: czy oglądana lista ofert to zapisane wyszukiwanie."""
    key = pracuj.search_key(url)
    with db.session() as conn:
        known = bool(key) and any(pracuj.same_search(r["url"], url)
                                  for r in conn.execute("select url from pracuj_searches where hidden = 0"))
    return {"known": known, "key": key}


class PracujAppIn(BaseModel):
    company: str
    title: str = ""
    url: str = ""
    applied_at: date | None = None


class PracujAppsIn(BaseModel):
    items: list[PracujAppIn]


@app.post("/api/pracuj/applications")
def pracuj_applications(body: PracujAppsIn):
    """Wtyczka: import listy „Moje aplikacje” z pracuj.pl; pomija to, co już jest w rejestrze."""
    added = 0
    with db.session() as conn:
        existing = [dict(r) for r in conn.execute("select company_key, title, url, applied_at from applications")]
        for it in body.items[:500]:
            if not it.company.strip():
                continue
            url = pracuj.clean_url(it.url) if pracuj.offer_id(it.url) else it.url.split("?")[0]
            ck, tk = db.company_key(it.company), db.title_key(it.title)
            when = (it.applied_at or date.today()).isoformat()
            dup = any(
                (url and e["url"] and pracuj.offer_id(e["url"]) and pracuj.offer_id(e["url"]) == pracuj.offer_id(url))
                or (e["company_key"] == ck and db.title_key(e["title"]) == tk and e["applied_at"][:10] == when)
                for e in existing
            )
            if dup:
                continue
            _insert_application(conn, ApplicationIn(
                company=it.company, title=it.title, url=url, applied_at=when, source="pracuj",
                note="" if it.applied_at else "import z pracuj.pl — data nieznana, wpisano dzień importu",
            ))
            existing.append({"company_key": ck, "title": it.title, "url": url, "applied_at": when})
            added += 1
        _link_applications(conn)
    return {"received": len(body.items), "added": added}


@app.get("/api/settings")
def get_settings():
    cfg = config.load()
    return {
        "config": {k: getattr(cfg, k) for k in config.Config.__dataclass_fields__ if k != "source"},
        "source": cfg.source,
        "categories": CATEGORIES,
        "cities": {k: v[0] for k, v in CITIES.items()},
        "big_cities": config.BIG_CITIES,
        "experience": config.EXPERIENCE,
    }


class SettingsIn(BaseModel):
    categories: list[str]
    cities: list[str] = []
    radius_km: int = 0
    remote: bool = True
    only_poland: bool = True
    experience: list[str] = []
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []
    exclude_companies: list[str] = []
    port: int = 8765


@app.post("/api/settings")
def save_settings(body: SettingsIn):
    """Zapis ustawień z przeglądarki do config.toml (z zachowaniem komentarzy i pełnych list do odznaczania)."""
    current = config.load()
    clean = lambda xs: [x.strip() for x in xs if x.strip()]
    cfg = config.Config(
        categories=body.categories, cities=body.cities, radius_km=max(0, min(body.radius_km, 500)),
        remote=body.remote, only_poland=body.only_poland,
        experience=[e for e in body.experience if e in config.EXPERIENCE],
        include_keywords=clean(body.include_keywords), exclude_keywords=clean(body.exclude_keywords),
        exclude_companies=clean(body.exclude_companies),
        browsers=current.browsers, extra_paths=current.extra_paths, port=body.port,
    )
    try:
        jjit.validate(cfg)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not 1024 <= cfg.port <= 65535:
        raise HTTPException(400, "Port musi być liczbą od 1024 do 65535")
    if not cfg.cities and not cfg.remote:
        raise HTTPException(400, "Wybierz co najmniej jedno miasto albo pracę zdalną")
    config.save(cfg)
    return {"ok": True, "restart_needed": cfg.port != current.port}


class ToggleIn(BaseModel):
    category: str


@app.post("/api/categories/toggle")
def toggle_category(body: ToggleIn):
    """Szybkie włączanie/wyłączanie kategorii z listy ofert (zapis do config.toml)."""
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Nieznana kategoria")
    cfg = config.load()
    chosen = set(cfg.categories) ^ {body.category}
    if not chosen:
        raise HTTPException(400, "Musi zostać włączona co najmniej jedna kategoria")
    cfg.categories = [c for c in CATEGORIES if c in chosen]
    config.save(cfg)
    return {"categories": cfg.categories, "enabled": body.category in chosen}


def _extension_version() -> str:
    return json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))["version"]


def _browser_path(path: Path) -> str:
    """Ścieżka do wskazania w oknie przeglądarki — pod WSL przeglądarka działa w Windows."""
    if "microsoft" not in platform.release().lower():
        return str(path)
    p = str(path)
    if p.startswith("/mnt/") and len(p) > 6:
        return f"{p[5].upper()}:\\" + p[7:].replace("/", "\\")
    return f"\\\\wsl.localhost\\{os.environ.get('WSL_DISTRO_NAME', 'Ubuntu')}" + p.replace("/", "\\")


@app.get("/api/extension")
def extension_info():
    return {"path": _browser_path(EXTENSION), "version": _extension_version()}


@app.get("/didIJJIT-extension.zip")
def extension_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(EXTENSION.iterdir()):
            if f.is_file():
                z.write(f, f"didIJJIT-extension/{f.name}")
    name = f"didIJJIT-extension-{_extension_version()}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
