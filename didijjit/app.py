"""didIJJIT — lokalna lista ofert z justjoin.it i rejestr wysłanych aplikacji."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, db, history, jjit

STATIC = Path(__file__).resolve().parent / "static"
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


def _link_applications(conn) -> None:
    """Oznacza oferty jako 'aplikowałem', jeśli aplikacja wskazuje tę samą ofertę (slug albo firma + stanowisko)."""
    for a in conn.execute("select * from applications where offer_guid is null").fetchall():
        slug = a["url"].rstrip("/").rsplit("/", 1)[-1].split("?")[0] if "justjoin.it/job-offer/" in a["url"] else None
        offer = conn.execute(
            "select guid from offers where slug = ? or (company_key = ? and lower(title) = lower(?) and ? != '') "
            "order by active desc limit 1",
            (slug, a["company_key"], a["title"], a["title"]),
        ).fetchone()
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
    cfg = config.load()
    return {
        "counts": counts,
        "applications": apps,
        "last_refresh": dict(last) if last else None,
        "config": {"source": cfg.source, "categories": cfg.categories, "cities": cfg.cities, "remote": cfg.remote},
    }


@app.post("/api/refresh")
def refresh():
    try:
        fetched = jjit.fetch_all(config.load())
    except Exception as exc:  # błąd sieci albo zmiana API po stronie justjoin.it
        raise HTTPException(502, f"Nie udało się pobrać ofert z justjoin.it: {exc}") from exc
    now = _now()
    with db.session() as conn:
        cur = conn.execute("insert into refreshes (at, fetched, added) values (?, ?, 0)", (now, len(fetched)))
        refresh_id = cur.lastrowid
        added = 0
        for o in fetched:
            exists = conn.execute("select 1 from offers where guid = ?", (o["guid"],)).fetchone()
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
                "delete from offers where last_seen_refresh is not ? and status = 'nowa' and note = '' "
                "and guid not in (select offer_guid from applications where offer_guid is not null)",
                (refresh_id,),
            )
            conn.execute("update offers set active = 0 where last_seen_refresh is not ?", (refresh_id,))
        conn.execute("update refreshes set added = ? where id = ?", (added, refresh_id))
        _link_applications(conn)
    return {"fetched": len(fetched), "added": added}


@app.get("/api/offers")
def offers(view: str = "nowe", q: str = ""):
    if view not in VIEWS:
        raise HTTPException(400, "Nieznany widok")
    with db.session() as conn:
        last = conn.execute("select max(id) from refreshes").fetchone()[0]
        sql = f"select * from offers where {VIEWS[view]}"
        args: list = []
        if q.strip():
            sql += " and (title like ? or company like ? or city like ?)"
            args += [f"%{q.strip()}%"] * 3
        sql += " order by published_at desc"
        rows = [dict(r) for r in conn.execute(sql, args)]
        history: dict[str, list[dict]] = {}
        for a in conn.execute("select * from applications order by applied_at desc"):
            history.setdefault(a["company_key"], []).append(dict(a))
    for r in rows:
        r["fresh"] = r["first_seen_refresh"] == last
        r["url"] = jjit.OFFER_URL.format(slug=r["slug"])
        r["company_history"] = [a for a in history.get(r["company_key"], []) if a["offer_guid"] != r["guid"]]
    return rows


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
                    (offer["company"], offer["company_key"], offer["title"], jjit.OFFER_URL.format(slug=offer["slug"]),
                     when, "oferta", guid),
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
    source: Literal["reczna", "historia", "wtyczka"] = "reczna"
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
def lookup(url: str, company: str = ""):
    """Dla wtyczki: czy ta oferta jest w bazie i czy aplikowałeś już do tej firmy."""
    slug = _jjit_slug(url)
    with db.session() as conn:
        offer = conn.execute("select * from offers where slug = ?", (slug,)).fetchone() if slug else None
        key = offer["company_key"] if offer else db.company_key(company) if company.strip() else None
        apps = [dict(a) for a in conn.execute(
            "select * from applications where company_key = ? or (url != '' and url = ?) order by applied_at desc",
            (key, url.split("?")[0]),
        )] if key or url else []
    # ta sama oferta bywa opublikowana w kilku kategoriach pod różnymi adresami — porównujemy też stanowisko
    same_title = lambda a: offer and a["company_key"] == offer["company_key"] and a["title"].lower() == offer["title"].lower()
    this_offer = [
        a for a in apps
        if (offer and a["offer_guid"] == offer["guid"]) or a["url"] == url.split("?")[0] or same_title(a)
    ]
    return {
        "offer": {k: offer[k] for k in ("guid", "title", "company", "status", "status_at")} if offer else None,
        "applied_here": this_offer[0] if this_offer else None,
        "company_history": [a for a in apps if a not in this_offer],
    }


class PageApplyIn(BaseModel):
    url: str
    company: str
    title: str = ""


@app.post("/api/applied-from-page")
def applied_from_page(body: PageApplyIn):
    """Wtyczka: użytkownik potwierdził, że wysłał CV na tej stronie."""
    slug = _jjit_slug(body.url)
    with db.session() as conn:
        offer = conn.execute("select guid from offers where slug = ?", (slug,)).fetchone() if slug else None
    if offer:
        return set_status(offer["guid"], StatusIn(status="aplikowalem"))
    with db.session() as conn:
        _insert_application(conn, ApplicationIn(
            company=body.company, title=body.title, url=body.url.split("?")[0], applied_at=date.today(), source="wtyczka",
        ))
        _link_applications(conn)
    return {"ok": True}
