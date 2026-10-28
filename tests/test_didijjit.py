from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from didijjit import config, db, history, jjit


def test_company_key_ignores_legal_forms_and_case():
    assert db.company_key("emagine Polska") == db.company_key("Emagine sp. z o.o.")
    assert db.company_key("ORLEN S.A.") == db.company_key("Orlen")
    assert db.company_key("Łódź Soft") == "lodzsoft"


def test_parse_offer_title():
    assert history.parse_offer_title("https://justjoin.it/job-offer/x", "Senior Python AI Engineer - Globex") == (
        "Senior Python AI Engineer", "Globex")
    assert history.parse_offer_title("https://www.linkedin.com/jobs/view/1", "PHP Developer | Initech | LinkedIn") == (
        "PHP Developer", "Initech")


def test_candidates_group_form_and_thank_you_with_offer_context():
    t0 = datetime(2026, 10, 22, 15, 40, tzinfo=timezone.utc)
    visits = [
        (t0, "https://justjoin.it/job-offer/umbrella-product-developer-warszawa-pm", "Product Developer - Umbrella"),
        (t0 + timedelta(minutes=2), "https://form.erecruiter.pl/form/abc", "Formularz aplikacyjny - Product Developer"),
        (t0 + timedelta(minutes=4), "https://form.erecruiter.pl/form/abc/thank-you", "Formularz"),
        (t0 + timedelta(minutes=10), "https://justjoin.it/job-offer/inna-oferta-gdansk-ai", "AI Engineer - Inna"),
    ]
    found = history.find_candidates(visits, now=t0 + timedelta(days=1))
    assert [c["kind"] for c in found] == ["wyslana", "obejrzana"]
    assert found[0]["company"] == "Umbrella" and found[0]["title"] == "Product Developer"
    assert found[1]["company"] == "Inna"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    from didijjit import app as app_module
    offers = [{
        "guid": "g1", "slug": "globex-senior-python-ai-engineer-gdynia-ai", "title": "Senior Python AI Engineer",
        "company": "Globex", "city": "Gdynia", "workplace": "hybrid", "experience": "senior", "category": "ai",
        "salary": "", "apply_url": "", "published_at": "2026-10-27T10:00:00Z",
    }, {
        "guid": "g2", "slug": "globex-ml-engineer-gdynia-ai", "title": "ML Engineer", "company": "Globex sp. z o.o.",
        "city": "Gdynia", "workplace": "remote", "experience": "mid", "category": "ai", "salary": "",
        "apply_url": "", "published_at": "2026-10-27T11:00:00Z",
    }]
    monkeypatch.setattr(app_module.jjit, "fetch_all", lambda cfg: offers)
    # zamiast dawnego wpisu startowego: aplikacja dodana ręcznie przed pierwszym odświeżeniem
    with TestClient(app_module.app) as c:
        c.post("/api/applications", json={
            "company": "Globex", "title": "Senior Python AI Engineer", "applied_at": "2026-10-27",
            "url": "https://justjoin.it/job-offer/globex-senior-python-ai-engineer-gdynia-ai",
        })
    with TestClient(app_module.app) as c:
        yield c


def test_refresh_links_seed_application_and_warns_about_company(client):
    assert client.post("/api/refresh").json() == {"fetched": 2, "added": 2}
    rows = {o["guid"]: o for o in client.get("/api/offers?view=aktywne").json()["offers"]}
    assert rows["g1"]["status"] == "aplikowalem"
    assert rows["g2"]["status"] == "nowa" and rows["g2"]["fresh"]
    assert rows["g2"]["company_history"][0]["title"] == "Senior Python AI Engineer"
    # drugie odświeżenie nie dodaje niczego nowego
    assert client.post("/api/refresh").json()["added"] == 0
    assert not client.get("/api/offers?view=nowe").json()["offers"][0]["fresh"]


def test_status_applied_creates_and_undo_removes_application(client):
    client.post("/api/refresh")
    client.post("/api/offers/g2/status", json={"status": "aplikowalem", "applied_at": "2026-10-28"})
    apps = client.get("/api/applications").json()
    assert any(a["offer_guid"] == "g2" and a["applied_at"] == "2026-10-28" for a in apps)
    client.post("/api/offers/g2/status", json={"status": "nie_interesuje"})
    assert not any(a["offer_guid"] == "g2" for a in client.get("/api/applications").json())


def test_history_import_adds_application_and_hides_dismissed(client, monkeypatch):
    monkeypatch.setattr(history, "history_files", lambda browsers, extra: [("brave", "x")])
    monkeypatch.setattr(history, "scan", lambda files: [
        {"key": "k1", "kind": "wyslana", "date": "2026-10-13", "title": "Mid AI Engineer", "company": "Hooli",
         "url": "https://justjoin.it/job-offer/hooli", "evidence": []},
        {"key": "k2", "kind": "obejrzana", "date": "2026-10-13", "title": "X", "company": "Y",
         "url": "https://justjoin.it/job-offer/y", "evidence": []},
    ])
    assert len(client.get("/api/history/candidates").json()["items"]) == 2
    client.post("/api/history/import", json={
        "items": [{"company": "Hooli", "title": "Mid AI Engineer", "url": "https://justjoin.it/job-offer/hooli",
                   "applied_at": "2026-10-13", "history_key": "k1"}],
        "dismiss": ["k2"],
    })
    assert client.get("/api/history/candidates").json()["items"] == []
    assert any(a["source"] == "historia" for a in client.get("/api/applications").json())


def test_late_thank_you_joins_earlier_form_and_other_thank_yous_are_ignored():
    t0 = datetime(2026, 10, 5, 19, 30, tzinfo=timezone.utc)
    visits = [
        (t0, "https://www.linkedin.com/jobs/view/4472728212/", "PHP Developer | Initech | LinkedIn"),
        (t0 + timedelta(minutes=5), "https://initech.traffit.com/public/form/a/51248c?source=linkedin.com", "PHP Developer"),
        (t0 + timedelta(days=6), "https://zrzutka.pl/vh644d/thank-you/01a0", "Dziękuję za Twoją wpłatę!"),
        (t0 + timedelta(days=8), "https://initech.traffit.com/public/form/thankyou/133", "Traffit"),
    ]
    found = history.find_candidates(visits, now=t0 + timedelta(days=9))
    assert len(found) == 1
    assert found[0]["kind"] == "wyslana" and found[0]["company"] == "Initech"
    assert found[0]["date"] == "2026-10-13"


def test_salary_uses_per_unit_rate():
    raw = [{"from": 15960, "fromPerUnit": 95, "to": 20160, "toPerUnit": 120, "currency": "PLN",
            "currencySource": "original", "type": "b2b", "unit": "Hour"}]
    assert jjit._salary(raw) == "95–120 PLN/h B2B"


def _raw(**kw):
    base = {"guid": "x", "slug": "x", "title": "Python Developer", "companyName": "Acme", "experienceLevel": "mid",
            "locations": [{"latitude": 54.35, "longitude": 18.65}]}
    return {**base, **kw}


def test_filters_from_config():
    cfg = config.Config(only_poland=True, experience=["mid", "senior"], exclude_keywords=["intern"],
                        exclude_companies=["Bad Corp sp. z o.o."])
    assert jjit.matches(_raw(), cfg)
    assert not jjit.matches(_raw(locations=[{"latitude": 34.05, "longitude": -118.24}]), cfg)  # Los Angeles
    assert jjit.matches(_raw(locations=[{"latitude": 40.4, "longitude": -3.7}, {"latitude": 52.2, "longitude": 21.0}]), cfg)
    assert not jjit.matches(_raw(experienceLevel="junior"), cfg)
    assert not jjit.matches(_raw(title="Python Intern"), cfg)
    assert not jjit.matches(_raw(companyName="Bad Corp"), cfg)
    assert not jjit.matches(_raw(), config.Config(include_keywords=["php"]))


def test_config_example_loads():
    cfg = config.load(config.EXAMPLE_PATH)
    assert cfg.categories == ["ai", "php", "python"] and cfg.only_poland and cfg.port == 8765
    assert [q for q in jjit.queries(cfg)] == [{"city": "trojmiasto"}, {"isRemote": "true"}]


def test_lookup_and_apply_from_extension(client):
    client.post("/api/refresh")
    url = "https://justjoin.it/job-offer/globex-ml-engineer-gdynia-ai"
    d = client.get("/api/lookup", params={"url": url}).json()
    assert d["offer"]["status"] == "nowa" and d["applied_here"] is None
    assert d["company_history"][0]["company"] == "Globex"
    client.post("/api/applied-from-page", json={"url": url, "company": "Globex", "title": "ML Engineer"})
    assert client.get("/api/lookup", params={"url": url}).json()["applied_here"]
    # oferta spoza bazy: wpis po nazwie firmy
    other = "https://justjoin.it/job-offer/nowa-firma-dev"
    client.post("/api/applied-from-page", json={"url": other, "company": "Nowa Firma", "title": "Dev"})
    assert client.get("/api/lookup", params={"url": other, "company": "Nowa Firma"}).json()["applied_here"]


def test_refresh_drops_untouched_offers_that_disappear(client, monkeypatch):
    from didijjit import app as app_module
    client.post("/api/refresh")
    client.post("/api/offers/g2/note", json={"note": "ciekawa"})
    monkeypatch.setattr(app_module.jjit, "fetch_all", lambda cfg: [{
        "guid": "g3", "slug": "s3", "title": "T", "company": "C", "city": "", "workplace": "", "experience": "",
        "category": "", "salary": "", "apply_url": "", "published_at": "",
    }])
    client.post("/api/refresh")
    guids = {o["guid"] for o in client.get("/api/offers?view=wygasle").json()["offers"]}
    assert guids == {"g1", "g2"}  # g1 ma aplikację, g2 notatkę; nietknięte by zniknęły


def test_lookup_treats_same_title_in_other_category_as_this_offer(client):
    client.post("/api/refresh")
    from didijjit import db as dbm
    with dbm.session() as conn:
        conn.execute("update offers set title = 'Senior Python AI Engineer' where guid = 'g2'")
    d = client.get("/api/lookup", params={"url": "https://justjoin.it/job-offer/globex-ml-engineer-gdynia-ai"}).json()
    assert d["applied_here"]["title"] == "Senior Python AI Engineer"


def test_radius_uses_whole_country_query_and_distance():
    cfg = config.Config(cities=["trojmiasto"], radius_km=40, remote=False)
    assert jjit.queries(cfg) == [{}]
    assert jjit.near(_raw(locations=[{"latitude": 54.60, "longitude": 18.23}]), cfg)  # Wejherowo, ok. 30 km
    assert not jjit.near(_raw(locations=[{"latitude": 54.16, "longitude": 19.40}]), cfg)  # Elbląg, ok. 60 km
    assert jjit.queries(config.Config(cities=["trojmiasto"], radius_km=0)) == [{"city": "trojmiasto"}, {"isRemote": "true"}]


def test_validate_rejects_typos():
    with pytest.raises(ValueError, match="pyhton"):
        jjit.validate(config.Config(categories=["pyhton"]))
    with pytest.raises(ValueError, match="gdanks"):
        jjit.validate(config.Config(cities=["gdanks"]))
    jjit.validate(config.load(config.EXAMPLE_PATH))


def test_example_lists_every_category_and_city():
    from didijjit.places import CATEGORIES, CITIES
    text = config.EXAMPLE_PATH.read_text(encoding="utf-8")
    assert all(f'"{c}",' in text for c in CATEGORIES)
    assert all(f'"{c}",' in text for c in CITIES)


def test_category_filter_and_sort(client):
    client.post("/api/refresh")
    d = client.get("/api/offers", params={"view": "aktywne", "category": "ai", "sort": "firma"}).json()
    assert d["categories"] == {"ai": 2} and len(d["offers"]) == 2
    assert client.get("/api/offers", params={"view": "aktywne", "category": "php"}).json()["offers"] == []
    assert client.get("/api/offers", params={"sort": "drop table"}).status_code == 400


def test_settings_roundtrip_keeps_commented_template(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    body = {"categories": ["java", "go"], "cities": ["krakow"], "radius_km": 25, "remote": False, "only_poland": True,
            "experience": ["senior"], "include_keywords": ["backend", " "], "exclude_keywords": ["intern"],
            "exclude_companies": ['Firma "X"'], "port": 8765}
    assert client.post("/api/settings", json=body).json()["restart_needed"] is False
    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert '  # "python",' in text and '  "java",' in text
    cfg = config.load(tmp_path / "config.toml")
    assert set(cfg.categories) == {"java", "go"}
    assert cfg.cities == ["krakow"] and cfg.radius_km == 25 and not cfg.remote
    assert cfg.include_keywords == ["backend"] and cfg.exclude_companies == ['Firma "X"']
    assert client.get("/api/settings").json()["config"]["experience"] == ["senior"]
    bad = client.post("/api/settings", json={**body, "categories": ["pyhton"]})
    assert bad.status_code == 400 and "pyhton" in bad.json()["detail"]


def test_example_config_is_rendered_from_defaults():
    assert config.EXAMPLE_PATH.read_text(encoding="utf-8") == config.render(config.Config())


def test_extension_zip_download(client):
    import io, zipfile
    r = client.get("/didIJJIT-extension.zip")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "didIJJIT-extension/manifest.json" in names and "didIJJIT-extension/detect.js" in names
