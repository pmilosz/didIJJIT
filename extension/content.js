// Pasek didIJJIT na stronach ofert justjoin.it.
(() => {
  const BAR_ID = "didijjit-bar";
  let lastUrl = "";
  let current = null; // { url, company, title }
  let askingFor = ""; // adres oferty, dla której wisi pytanie „Wysłałeś CV?”

  const isOffer = () => location.pathname.startsWith("/job-offer/");
  // wersja z callbackiem działa tak samo w Chromium i Firefoksie
  const send = (msg) => new Promise((res) => chrome.runtime.sendMessage(msg, (r) => res(r || { ok: false, offline: true })));
  const day = (iso) => new Date(iso.length === 10 ? iso + "T12:00" : iso).toLocaleDateString("pl-PL");

  const offerPath = () => location.pathname.split("/").slice(0, 3).join("/");

  // dane strukturalne JobPosting — najpewniejsze źródło nazwy firmy
  function jsonLd() {
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const d = JSON.parse(s.textContent);
        const items = Array.isArray(d) ? d : d["@graph"] || [d];
        const job = items.find((x) => x && x["@type"] === "JobPosting");
        if (job) return { title: job.title || "", company: job.hiringOrganization?.name || "" };
      } catch {}
    }
    return null;
  }

  // tytuł karty ma postać „Stanowisko - Firma”, czasem z dopiskiem po „|”
  function fromTitle(text) {
    const raw = (text || "").split(" | ")[0];
    const i = raw.lastIndexOf(" - ");
    return i > 0 ? { title: raw.slice(0, i).trim(), company: raw.slice(i + 3).trim() } : null;
  }

  function pageInfo() {
    const h1 = document.querySelector("h1")?.textContent?.trim();
    const ld = jsonLd();
    const og = document.querySelector('meta[property="og:title"]')?.content;
    // po przejściu między ofertami bez przeładowania JSON-LD bywa jeszcze z poprzedniej oferty
    const ldOk = ld?.company && (!h1 || !ld.title || ld.title.trim() === h1);
    const t = fromTitle(document.title) || fromTitle(og);
    const info = {
      url: location.origin + offerPath(),
      title: h1 || t?.title || "",
      company: (ldOk && ld.company) || t?.company || "",
    };
    // ta sama oferta (np. otwarty formularz aplikacji) — nie gubimy rozpoznanej wcześniej firmy
    if (current && current.url === info.url) {
      info.company ||= current.company;
      info.title ||= current.title;
    }
    return info;
  }

  function bar() {
    let el = document.getElementById(BAR_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = BAR_ID;
      document.documentElement.appendChild(el);
    }
    return el;
  }

  function show(kind, html, actions = []) {
    const el = bar();
    el.className = `jr-${kind}`;
    el.innerHTML = `<span class="jr-logo">didIJJIT?</span><span class="jr-text">${html}</span>`;
    for (const [label, fn] of actions) {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = fn;
      el.appendChild(b);
    }
    const close = document.createElement("button");
    close.className = "jr-close";
    close.textContent = "×";
    close.title = "Ukryj";
    close.onclick = () => el.remove();
    el.appendChild(close);
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function check() {
    if (!isOffer()) { askingFor = ""; document.getElementById(BAR_ID)?.remove(); return; }
    current = pageInfo();
    // pytanie po kliknięciu „Aplikuj” ma pierwszeństwo — nie nadpisujemy go zwykłym sprawdzeniem
    if (askingFor === current.url && document.getElementById(BAR_ID)) return;
    askingFor = "";
    const r = await send({ type: "lookup", url: current.url, company: current.company });
    if (r.offline) {
      show("off", `nie działa na ${esc(r.base)} — uruchom program, żeby widzieć historię aplikacji.`);
      return;
    }
    const d = r.data;
    if (d.offer?.company) current.company = d.offer.company;
    if (d.applied_here) {
      show("done", `Aplikowałeś na tę ofertę <b>${day(d.applied_here.applied_at)}</b>.`);
    } else if (d.company_history.length) {
      const list = d.company_history.slice(0, 3).map((a) => `${day(a.applied_at)}${a.title ? " – " + esc(a.title) : ""}`).join("; ");
      show("warn", `Już aplikowałeś do <b>${esc(current.company)}</b>: ${list}`, [["Zapisz tę aplikację", markApplied]]);
    } else {
      document.getElementById(BAR_ID)?.remove();
    }
  }

  async function markApplied() {
    current = pageInfo();
    if (!current.company) {
      // ostateczność: strona nie podała nazwy firmy w żadnym znanym miejscu
      const c = prompt("didIJJIT nie rozpoznał nazwy firmy na tej stronie.\nWpisz ją, żeby zapisać aplikację:", "");
      if (!c) return;
      current.company = c;
    }
    askingFor = "";
    const r = await send({ type: "applied", ...current });
    if (r.ok) show("done", `Zapisano: aplikowałeś do <b>${esc(current.company)}</b> dzisiaj.`);
    else show("off", "Nie udało się zapisać — czy program didIJJIT działa?");
  }

  // po kliknięciu „Aplikuj” pytamy, czy CV naprawdę poszło — wysłanie dzieje się w formularzu firmy
  // przycisk „Aplikuj” — także gdy kliknięto ikonę/napis w środku albo element z role="button"
  function applyButton(e) {
    for (const n of e.composedPath()) {
      if (!(n instanceof Element)) continue;
      if (n.id === BAR_ID) return null; // kliknięcia w nasz własny pasek
      if (!n.matches('a,button,[role="button"]')) continue;
      const label = `${n.innerText || n.textContent || ""} ${n.getAttribute("aria-label") || ""} ${n.title || ""}`;
      return /aplikuj|apply/i.test(label) ? n : null;
    }
    return null;
  }

  document.addEventListener("click", (e) => {
    if (!isOffer() || !applyButton(e)) return;
    setTimeout(() => {
      if (!isOffer()) return;
      if (!current || current.url !== location.origin + offerPath()) current = pageInfo();
      askingFor = current.url;
      show("ask", `Wysłałeś CV do <b>${esc(current.company || "tej firmy")}</b>?`, [
        ["Tak, zapisz", markApplied],
        ["Jeszcze nie", () => { askingFor = ""; document.getElementById(BAR_ID)?.remove(); }],
      ]);
    }, 400);
  }, true);

  // justjoin.it to aplikacja jednostronicowa — adres zmienia się bez przeładowania.
  // Liczy się tylko ścieżka oferty: górny „Aplikuj” zmienia sam dopisek w adresie
  // (formularz / kotwica) i wcześniej to kasowało pasek z pytaniem.
  setInterval(() => {
    const key = location.pathname.startsWith("/job-offer/") ? offerPath() : location.pathname;
    if (key !== lastUrl) {
      lastUrl = key;
      setTimeout(check, 800); // czekamy, aż strona ustawi tytuł oferty
    }
  }, 500);
})();
