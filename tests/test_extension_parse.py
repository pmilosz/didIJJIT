"""Odczyt ofert i aplikacji ze stron pracuj.pl (extension/pracuj-parse.js), uruchamiany w Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

PARSER = Path(__file__).resolve().parent.parent / "extension" / "pracuj-parse.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="brak Node.js")


def run(expr: str, data) -> object:
    script = f"const P = require({json.dumps(str(PARSER))}); const data = {json.dumps(data)};" \
             f"process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


NEXT_DATA = {"props": {"pageProps": {"data": {"jobOffers": {"groupedOffers": [
    {"groupId": "g1", "jobTitle": "Python Developer", "companyName": "Globex Sp. z o.o.",
     "salaryDisplayText": "15 000–20 000 zł netto (+ VAT) / mies.", "workModes": ["praca hybrydowa"],
     "positionLevels": ["specjalista (Mid / Regular)"], "lastPublicated": "2026-11-10T08:00:00Z",
     "offers": [{"partitionId": 1, "displayWorkplace": "Gdańsk",
                 "offerAbsoluteUri": "https://www.pracuj.pl/praca/python-developer-gdansk,oferta,1004000001"}]},
    {"groupId": "g2", "jobTitle": "Data Engineer", "companyName": "Initech",
     "offers": [{"offerAbsoluteUri": "https://www.pracuj.pl/praca/data-engineer,oferta,1004000002?s=x"}]},
    # bez adresu oferty — to nie jest oferta
    {"jobTitle": "Reklama", "companyName": "Ktoś"},
]}}, "page": {"title": "Oferty pracy", "url": "https://www.pracuj.pl/praca"}}}}

LD = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Python Developer",
      "hiringOrganization": {"@type": "Organization", "name": "Globex"},
      "url": "https://www.pracuj.pl/praca/python-developer-gdansk,oferta,1004000001"}

APPS = {"applications": [
    {"applicationDate": "02.11.2026", "offer": {"jobTitle": "Backend Developer", "companyName": "Initech",
                                                "offerUrl": "https://www.pracuj.pl/praca/backend,oferta,1003999999"}},
    {"sentDate": "5 października 2026", "position": "QA", "employer": {"name": "Hooli"},
     "link": "https://www.pracuj.pl/praca/qa,oferta,1003000000"},
]}


def test_grouped_offers_from_next_data():
    offers = run("P.fromJson([data])", NEXT_DATA)
    assert [o["id"] for o in offers] == ["1004000001", "1004000002"]
    o = offers[0]
    assert o["title"] == "Python Developer" and o["company"] == "Globex Sp. z o.o." and o["city"] == "Gdańsk"
    assert o["workplace"] == "praca hybrydowa" and o["published_at"].startswith("2026-11-10")
    assert offers[1]["url"] == "https://www.pracuj.pl/praca/data-engineer,oferta,1004000002"


def test_json_ld_and_duplicates_across_sources():
    offers = run("P.fromJson([data.ld, data.next])", {"ld": LD, "next": NEXT_DATA})
    assert len(offers) == 2 and offers[0]["company"] == "Globex"


def test_applications_with_dates():
    apps = run("P.fromJson([data])", APPS)
    assert [(a["company"], a["title"], a["applied_at"]) for a in apps] == [
        ("Initech", "Backend Developer", "2026-11-02"), ("Hooli", "QA", "2026-10-05")]


def test_dates():
    assert run("['2026-01-03T10:00', 'wysłano 7.3.2026', 'dzisiaj', 'coś'].map((s) => P.toDate(s, new Date(2026, 10, 12)))",
               None) == ["2026-01-03", "2026-03-07", "2026-11-12", ""]


def test_saved_searches_from_job_alerts():
    # budowa jak na pracuj.pl: props.pageProps.dehydratedState.queries[].state.data (zalogowany użytkownik)
    page = {"props": {"pageProps": {"dehydratedState": {"queries": [{"queryKey": ["jobAlerts"], "state": {"data": [
        {"id": "a1", "name": "php", "criteria": [{"key": "kw", "value": "php"}],
         "jobAlertOffersAbsoluteUri": "https://inzynieria.pracuj.pl/praca?kw=php"},
        {"id": "a2", "name": "php - Gdynia + 30 km",
         "jobAlertOffersAbsoluteUri": "https://inzynieria.pracuj.pl/praca?kw=php&rd=30&wp=Gdynia"},
    ]}}, {"queryKey": ["jobOffers"], "state": {"data": {"groupedOffers": [], "offersTotalCount": 0}}}]}}}}
    assert run("P.jobAlerts([data])", page) == [
        {"url": "https://inzynieria.pracuj.pl/praca?kw=php", "name": "php"},
        {"url": "https://inzynieria.pracuj.pl/praca?kw=php&rd=30&wp=Gdynia", "name": "php - Gdynia + 30 km"}]
    assert run("P.fromJson([data])", page) == []
