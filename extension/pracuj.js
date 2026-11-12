// Pasek didIJJIT na pracuj.pl. Wtyczka czyta tylko strony, które sam otwierasz — niczego nie pobiera w tle.
//  • oferta: „już aplikowałeś do tej firmy / na to stanowisko” + pytanie po kliknięciu „Aplikuj”;
//  • lista ofert (zapisane wyszukiwanie): oferty trafiają do didIJJIT, przy firmach, gdzie już aplikowałeś, pojawia się znaczek;
//  • zapisane wyszukiwania: import adresów do didIJJIT;
//  • moje aplikacje: import wysłanych aplikacji do rejestru didIJJIT.
(() => {
  const { api, day, esc, hide, show, applyButton, storage } = globalThis.didijjit;
  const P = globalThis.didijjitParse;
  const PENDING = "pracujPendingApply";
  const PENDING_TTL = 2 * 3600e3; // pytanie „Wysłałeś CV?” czeka 2 godziny, także po przejściu do formularza
  let lastUrl = "", runId = 0, current = null;

  // brak programu albo stara wersja programu (bez obsługi pracuj.pl) — mówimy to wprost zamiast milczeć
  function offline(r) {
    if (r.offline) { show("off", "nie działa — uruchom program, żeby widzieć historię aplikacji."); return true; }
    if (!r.ok && r.data?.detail === "Not Found") {
      show("off", "program didIJJIT jest w starszej wersji — zamknij go i uruchom ponownie (run.bat / run.sh), żeby działał na pracuj.pl.");
      return true;
    }
    return false;
  }

  // ===== odczyt strony =====
  function jsonRoots() {
    const roots = [];
    for (const s of document.querySelectorAll('script#__NEXT_DATA__, script[type="application/ld+json"], script[type="application/json"]')) {
      try { roots.push(JSON.parse(s.textContent)); } catch {}
    }
    return roots;
  }

  // oferty polecane („Oferty rekomendowane dla Ciebie”, „Zobacz też”) to nie wyniki wyszukiwania
  const RECOMMENDED = '[data-test="recommended-offer"], [data-test="section-recommended-offers"], [data-test="more-offers-box"], [data-test*="recommend"]';

  // karty ofert w HTML: <div data-test="default-offer" data-test-offerid="…"> z polami data-test="offer-title" itd.
  function fromDom() {
    const out = new Map();
    const cards = [...document.querySelectorAll("[data-test-offerid]")];
    // zapasowo: dowolne linki „…,oferta,123”, gdy strona nie ma znaczników kart
    if (!cards.length) document.querySelectorAll('a[href*=",oferta,"]').forEach((a) => cards.push(a.closest("article, li") || a.parentElement?.parentElement));
    for (const card of cards) {
      if (!card || card.closest(RECOMMENDED)) continue;
      const link = card.querySelector('a[data-test="link-offer"], a[href*=",oferta,"]') || (card.matches("a") ? card : null);
      const id = card.dataset.testOfferid || P.offerId(link?.href);
      if (!id || out.has(id)) continue;
      const pick = (sel) => (card.querySelector(sel)?.textContent || "").replace(/\s+/g, " ").trim();
      const title = pick('[data-test="offer-title"], [data-test="link-offer-title"], h2, h3') ||
        (link?.title || "").replace(/^Zobacz ofertę\s*/i, "");
      const company = pick('[data-test="text-company-name"], [data-test*="company-name"], [data-test*="employer"]');
      const url = P.offerId(link?.href) ? P.cleanUrl(link.href) : `https://www.pracuj.pl/praca/oferta,oferta,${id}`;
      if (!title || !company || title.length > 200) continue;
      out.set(id, { id, url, title, company, city: pick('[data-test="text-region"]'), workplace: pick('[data-test="offer-additional-info-0"]'),
        experience: "", salary: pick('[data-test="offer-salary"]'), published_at: "", applied_at: P.toDate(card.textContent) });
    }
    return [...out.values()];
  }

  function items() {
    const recommended = new Set([...document.querySelectorAll("[data-test-offerid]")]
      .filter((c) => c.closest(RECOMMENDED)).map((c) => c.dataset.testOfferid));
    const fromJs = P.fromJson(jsonRoots()).filter((x) => !recommended.has(x.id));
    // dopełniamy tym, co widać w HTML (np. dane doładowane po wejściu na stronę)
    const ids = new Set(fromJs.map((x) => x.id));
    return [...fromJs, ...fromDom().filter((x) => !ids.has(x.id))];
  }

  function offerInfo(id) {
    const own = items().find((x) => x.id === id);
    const h1 = document.querySelector('h1[data-test*="position"], h1')?.textContent?.trim() || "";
    const comp = document.querySelector('[data-test*="employer-name"], [data-test*="employerName"], [data-test*="company-name"]')
      ?.textContent?.trim().replace(/\s*O firmie\s*$/i, "") || "";
    // tytuł karty: „Stanowisko - Firma - Miasto | Pracuj.pl” (zapas, gdy nic innego nie zadziała)
    const parts = document.title.split("|")[0].split(" - ").map((x) => x.trim());
    return {
      url: P.cleanUrl(location.href),
      title: own?.title || h1 || parts[0] || "",
      company: own?.company || comp || parts[1] || "",
    };
  }

  // ===== typy stron =====
  const isOffer = () => !!P.offerId(location.href);
  const isApplications = () => /aplikacj|applications/i.test(location.pathname) && !isOffer();
  const isSavedSearches = () => /wyszukiwan|subskrypc|powiadomie|alert|saved-search/i.test(location.pathname) && !isOffer();

  async function offerPage() {
    current = offerInfo(P.offerId(location.href));
    const r = await api(`/api/lookup?${new URLSearchParams({ url: current.url, company: current.company, title: current.title })}`);
    if (offline(r)) return;
    const d = r.data;
    if (d.offer?.company) current.company = d.offer.company;
    if (d.applied_here) {
      show("done", `Aplikowałeś na tę ofertę <b>${day(d.applied_here.applied_at)}</b>.`);
    } else if (d.company_history?.length) {
      const list = d.company_history.slice(0, 3).map((a) => `${day(a.applied_at)}${a.title ? " – " + esc(a.title) : ""}`).join("; ");
      show("warn", `Już aplikowałeś do <b>${esc(current.company)}</b>: ${list}`, [["Zapisz tę aplikację", () => markApplied(current)]]);
    } else hide();
  }

  async function markApplied(info) {
    if (!info.company) {
      const c = prompt("didIJJIT nie rozpoznał nazwy firmy na tej stronie.\nWpisz ją, żeby zapisać aplikację:", "");
      if (!c) return;
      info.company = c;
    }
    await storage.set(PENDING, null);
    const r = await send("/api/applied-from-page", info);
    if (r.ok) show("done", `Zapisano: aplikowałeś do <b>${esc(info.company)}</b> dzisiaj.`);
    else show("off", "Nie udało się zapisać — czy program didIJJIT działa?");
  }
  const send = (path, body) => api(path, body);

  // wszystkie oferty na stronie (także polecane) — do znaczków „już aplikowałeś do tej firmy”
  function allCards() {
    const out = [];
    for (const card of document.querySelectorAll("[data-test-offerid]")) {
      const company = card.querySelector('[data-test="text-company-name"]')?.textContent?.trim();
      if (company) out.push({ id: card.dataset.testOfferid, company });
    }
    return out;
  }

  async function markCompanies(found) {
    const all = [...found, ...allCards()];
    if (!all.length) return true;
    const r = await api("/api/companies/applied", { companies: [...new Set(all.map((x) => x.company))] });
    if (offline(r)) return false;
    const applied = r.data || {};
    for (const it of all) {
      if (!applied[it.company]) continue;
      const cards = document.querySelectorAll(`[data-test-offerid="${it.id}"]`);
      const spots = cards.length ? [...cards].map((c) => c.querySelector('[data-test="offer-title"]') || c.querySelector('[data-test="text-company-name"]')).filter(Boolean)
        : [...document.querySelectorAll(`a[href*=",oferta,${it.id}"]`)].slice(0, 1);
      for (const a of spots) {
        if (a.dataset.didijjit) continue;
        a.dataset.didijjit = "1";
        const b = document.createElement("span");
        b.className = "didijjit-badge";
        b.textContent = `✓ aplikowałeś do tej firmy ${day(applied[it.company])}`;
        a.insertAdjacentElement("afterend", b);
      }
    }
    return true;
  }

  async function listPage(found) {
    if (!(await markCompanies(found))) return;
    const zero = !found.length && !!document.querySelector('[data-test="zero-offers-section"]');
    if (!found.length && !zero) {
      // strona wyszukiwania, ale nie rozpoznano żadnej oferty — lepiej powiedzieć niż milczeć
      if ((await api(`/api/pracuj/search-known?${new URLSearchParams({ url: location.href })}`)).data?.key) {
        show("off", "nie rozpoznał ofert na tej stronie wyszukiwania. Zapisz stronę (Ctrl+S) i zgłoś to — trzeba dopasować odczyt do pracuj.pl.");
      }
      return;
    }
    const known = (await api(`/api/pracuj/search-known?${new URLSearchParams({ url: location.href })}`)).data || {};
    const save = async () => {
      const s = await api("/api/pracuj/offers", { offers: found, search_url: location.href });
      return s.ok ? s.data : null;
    };
    if (zero) {
      show(known.known ? "done" : "warn", `To wyszukiwanie nie ma teraz ofert${location.hostname.startsWith("www.") ? "" :
        ` w serwisie <b>${esc(location.hostname)}</b> — spróbuj tego samego wyszukiwania na www.pracuj.pl (wszystkie kategorie)`}.` +
        " Oferty polecane przez pracuj.pl nie trafiają do didIJJIT.");
      return;
    }
    if (known.known) {
      const s = await save();
      if (s) {
        show("done", `Zapisane wyszukiwanie: ${s.received} ofert na tej stronie, nowych w didIJJIT: <b>${s.added}</b>.`);
        setTimeout(() => document.querySelector("#didijjit-bar.jr-done") && hide(), 6000);
      }
    } else if (known.key) {
      show("ask", `Na tej stronie jest ${found.length} ofert. Dodać to wyszukiwanie do listy ofert didIJJIT?`, [
        ["Dodaj wyszukiwanie", async () => {
          const name = document.querySelector("h1")?.textContent?.trim() || document.title.split("|")[0].trim();
          await api("/api/pracuj/searches", { searches: [{ url: location.href, name }] });
          const s = await save();
          if (s) show("done", `Dodano. Ofert: ${s.received}, nowych w didIJJIT: <b>${s.added}</b>. Przy kolejnych wizytach oferty zapiszą się same.`);
          else show("off", "Nie udało się zapisać — czy program didIJJIT działa?");
        }],
      ]);
    }
  }

  async function applicationsPage(found) {
    if (!found.length) return;
    show("ask", `Na tej stronie jest ${found.length} Twoich aplikacji z pracuj.pl. Zapisać je w didIJJIT (bez duplikatów)?`, [
      ["Pokaż i zapisz", async () => {
        const preview = found.slice(0, 25).map((a) => `• ${a.applied_at || "?"} ${a.company} – ${a.title}`).join("\n");
        if (!confirm(`didIJJIT zapisze ${found.length} aplikacji:\n\n${preview}${found.length > 25 ? "\n…" : ""}\n\nZapisać?`)) return;
        const r = await api("/api/pracuj/applications", {
          items: found.map((a) => ({ company: a.company, title: a.title, url: a.url, applied_at: a.applied_at || null })),
        });
        if (r.ok) show("done", `Zapisano nowych aplikacji: <b>${r.data.added}</b> (pominięte jako już znane: ${r.data.received - r.data.added}).`);
        else show("off", "Nie udało się zapisać — czy program didIJJIT działa?");
      }],
    ]);
  }

  function savedSearchesPage() {
    const found = new Map();
    for (const a of document.querySelectorAll('a[href*="pracuj.pl"]')) {
      if (P.offerId(a.href) || !/\/praca\b|[?&](kw|its|wm|et|tc|rd|sal)=/i.test(a.href)) continue;
      if (!found.has(a.href)) found.set(a.href, (a.textContent || "").trim().slice(0, 200));
    }
    if (!found.size) return false;
    show("ask", `Znaleziono zapisane wyszukiwania: ${found.size}. Zaimportować je do didIJJIT?`, [
      ["Importuj", async () => {
        const r = await api("/api/pracuj/searches", { searches: [...found].map(([url, name]) => ({ url, name })) });
        if (r.ok) show("done", `Dodano wyszukiwań: <b>${r.data.added}</b>. Otwórz je w programie (zakładka pracuj.pl), żeby zebrać oferty.`);
        else show("off", "Nie udało się zapisać — czy program didIJJIT działa?");
      }],
    ]);
    return true;
  }

  // pytanie „Wysłałeś CV?” — przeżywa przejście do formularza aplikacji na innej stronie
  async function pendingAsk() {
    const p = await storage.get(PENDING);
    if (!p || Date.now() - p.at > PENDING_TTL) return false;
    show("ask", `Wysłałeś CV do <b>${esc(p.company || "tej firmy")}</b>${p.title ? ` (${esc(p.title)})` : ""}?`, [
      ["Tak, zapisz", () => markApplied(p)],
      ["Jeszcze nie", async () => { await storage.set(PENDING, null); hide(); }],
    ]);
    return true;
  }

  // zapisane wyszukiwania z konta pracuj.pl trafiają do didIJJIT same (raz na wizytę w serwisie)
  let alertsDone = false;
  async function importAlerts() {
    if (alertsDone) return false;
    const alerts = P.jobAlerts(jsonRoots());
    if (!alerts.length) return false;
    alertsDone = true;
    const r = await api("/api/pracuj/searches", { searches: alerts, auto: true });
    if (offline(r) || !r.data?.added) return !r.ok;
    show("done", `Zaimportowano zapisane wyszukiwania z pracuj.pl: <b>${r.data.added}</b>. Otwieraj je z zakładki <b>pracuj.pl</b> w programie — oferty zapiszą się same.`);
    return true;
  }

  async function route() {
    const my = ++runId;
    if (await pendingAsk()) return;
    if (my !== runId) return;
    if (isOffer()) return offerPage();
    if (await importAlerts()) return;
    if (isSavedSearches() && savedSearchesPage()) return;
    const found = items();
    if (isApplications()) return applicationsPage(found);
    return listPage(found);
  }

  document.addEventListener("click", (e) => {
    if (!isOffer() || !applyButton(e)) return;
    const info = current && current.url === P.cleanUrl(location.href) ? current : offerInfo(P.offerId(location.href));
    storage.set(PENDING, { ...info, at: Date.now() }).then(() => setTimeout(pendingAsk, 400));
  }, true);

  // pracuj.pl bywa aplikacją jednostronicową — sprawdzamy zmianę adresu; dane listy doładowują się chwilę po wejściu
  setInterval(() => {
    if (location.href === lastUrl) return;
    lastUrl = location.href;
    setTimeout(route, 1200);
    setTimeout(() => !document.getElementById("didijjit-bar") && route(), 4000);
  }, 500);
})();
