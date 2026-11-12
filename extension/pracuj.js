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

  const offline = (r) => r.offline && (show("off", "nie działa — uruchom program, żeby widzieć historię aplikacji."), true);

  // ===== odczyt strony =====
  function jsonRoots() {
    const roots = [];
    for (const s of document.querySelectorAll('script#__NEXT_DATA__, script[type="application/ld+json"], script[type="application/json"]')) {
      try { roots.push(JSON.parse(s.textContent)); } catch {}
    }
    return roots;
  }

  // zapasowo: karty ofert w HTML (linki „…,oferta,123”), gdy strona nie ma danych w JSON-ie
  function fromDom() {
    const out = new Map();
    for (const a of document.querySelectorAll('a[href*=",oferta,"]')) {
      const id = P.offerId(a.href);
      if (!id || out.has(id)) continue;
      const card = a.closest('[data-test*="offer"], article, li') || a.parentElement?.parentElement;
      if (!card) continue;
      const pick = (sel) => card.querySelector(sel)?.textContent?.trim() || "";
      const title = pick('[data-test*="title"], [data-test*="position"], h2, h3') || a.textContent.trim();
      const company = pick('[data-test*="company"], [data-test*="employer"]');
      if (!title || !company || title.length > 200) continue;
      out.set(id, { id, url: P.cleanUrl(a.href), title, company, city: pick('[data-test*="location"], [data-test*="workplace"]'),
        workplace: "", experience: "", salary: pick('[data-test*="salary"]'), published_at: "", applied_at: P.toDate(card.textContent) });
    }
    return [...out.values()];
  }

  function items() {
    const fromJs = P.fromJson(jsonRoots());
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

  async function listPage(found) {
    // znaczki przy firmach, do których już wysłano CV
    const r = await api("/api/companies/applied", { companies: [...new Set(found.map((x) => x.company))] });
    if (offline(r)) return;
    const applied = r.data || {};
    for (const it of found) {
      if (!applied[it.company]) continue;
      for (const a of document.querySelectorAll(`a[href*=",oferta,${it.id}"]`)) {
        if (a.dataset.didijjit) continue;
        a.dataset.didijjit = "1";
        const b = document.createElement("span");
        b.className = "didijjit-badge";
        b.textContent = `✓ aplikowałeś do tej firmy ${day(applied[it.company])}`;
        a.insertAdjacentElement("afterend", b);
      }
    }
    const known = (await api(`/api/pracuj/search-known?${new URLSearchParams({ url: location.href })}`)).data || {};
    const save = async () => {
      const s = await api("/api/pracuj/offers", { offers: found, search_url: location.href });
      return s.ok ? s.data : null;
    };
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

  async function route() {
    const my = ++runId;
    if (await pendingAsk()) return;
    if (my !== runId) return;
    if (isOffer()) return offerPage();
    if (isSavedSearches() && savedSearchesPage()) return;
    const found = items();
    if (isApplications()) return applicationsPage(found);
    if (found.length) return listPage(found);
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
