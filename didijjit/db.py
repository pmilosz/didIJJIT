"""Baza SQLite: oferty, aplikacje, odświeżenia i sprawdzone pozycje z historii przeglądarek."""
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("DIDIJJIT_DB", Path(__file__).resolve().parent.parent / "data" / "didijjit.db"))

SCHEMA = """
create table if not exists offers (
    guid text primary key,
    slug text not null,
    title text not null,
    company text not null,
    company_key text not null,
    city text,
    workplace text,
    experience text,
    category text,
    salary text,
    apply_url text,
    published_at text,
    first_seen_at text not null,
    first_seen_refresh integer,
    last_seen_at text not null,
    last_seen_refresh integer,
    active integer not null default 1,
    status text not null default 'nowa',
    status_at text,
    note text not null default ''
);
create index if not exists offers_company on offers(company_key);

create table if not exists applications (
    id integer primary key autoincrement,
    company text not null,
    company_key text not null,
    title text not null default '',
    url text not null default '',
    applied_at text not null,
    source text not null,
    offer_guid text,
    note text not null default '',
    created_at text not null default (datetime('now'))
);
create index if not exists applications_company on applications(company_key);

create table if not exists refreshes (
    id integer primary key autoincrement,
    at text not null,
    fetched integer not null,
    added integer not null
);

create table if not exists history_dismissed (
    key text primary key
);
"""

# końcówki form prawnych i dopiski, które różnią zapis tej samej firmy
_SUFFIXES = re.compile(
    r"\b(sp\.? ?z ?o\.? ?o\.?|spółka z ograniczoną odpowiedzialnością|s\.? ?a\.?|sp\.? ?k\.?|"
    r"sp\.? ?j\.?|ltd\.?|llc|inc\.?|gmbh|b\.?v\.?|polska|poland|group|technology|technologies)\b",
    re.IGNORECASE,
)


def company_key(name: str) -> str:
    """Klucz do porównywania firm: bez form prawnych, polskich znaków i interpunkcji."""
    s = _SUFFIXES.sub(" ", name.lower()).replace("ł", "l")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s or re.sub(r"[^a-z0-9]+", "", name.lower())


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("pragma table_info(offers)")}
        if "last_seen_refresh" not in cols:
            conn.execute("alter table offers add column last_seen_refresh integer")
            conn.execute("update offers set last_seen_refresh = first_seen_refresh")
        # starsza nazwa tabeli z czasów, gdy import obsługiwał tylko Brave
        if conn.execute("select 1 from sqlite_master where name = 'brave_dismissed'").fetchone():
            conn.execute("insert or ignore into history_dismissed (key) select key from brave_dismissed")
            conn.execute("drop table brave_dismissed")
