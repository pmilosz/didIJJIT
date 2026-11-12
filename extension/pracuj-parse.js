// Odczyt ofert i aplikacji ze strony pracuj.pl — czyste funkcje bez DOM (testowane w tests/test_extension_parse.py).
// Najpewniejsze źródło to dane, które strona ma w sobie w JSON-ie (Next.js __NEXT_DATA__, JSON-LD).
// Nazwy pól różnią się między stronami, więc szukamy obiektów, które wyglądają jak oferta: stanowisko + firma + adres oferty.
globalThis.didijjitParse = (() => {
  const OFFER_RE = /^https?:\/\/([a-z0-9-]+\.)*pracuj\.pl\/.*,oferta,(\d+)/i;
  const offerId = (url) => (OFFER_RE.exec(String(url || "").trim()) || [])[2] || null;
  const cleanUrl = (url) => String(url || "").trim().split("?")[0].split("#")[0];

  const str = (v) => (typeof v === "string" ? v.trim() : typeof v === "number" ? String(v) : "");
  const first = (...vals) => vals.map(str).find(Boolean) || "";
  const list = (v) => (Array.isArray(v) ? v.map((x) => str(x) || str(x?.name) || str(x?.value)).filter(Boolean).join(", ") : str(v));

  const MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"];
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

  // data aplikacji w formacie RRRR-MM-DD albo "", gdy nie da się jej odczytać
  function toDate(v, now = new Date()) {
    const s = str(v).toLowerCase();
    if (!s) return "";
    let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (m) return `${m[1]}-${m[2]}-${m[3]}`;
    m = /(\d{1,2})\.(\d{1,2})\.(\d{4})/.exec(s);
    if (m) return `${m[3]}-${pad(m[2])}-${pad(m[1])}`;
    m = /(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})/.exec(s);
    if (m && MONTHS.includes(m[2])) return `${m[3]}-${pad(MONTHS.indexOf(m[2]) + 1)}-${pad(m[1])}`;
    if (/\bdzisiaj|\bdziś/.test(s)) return iso(now);
    if (/\bwczoraj/.test(s)) return iso(new Date(now.getTime() - 864e5));
    return "";
  }

  // adres oferty w obiekcie albo w jego najbliższych dzieciach (np. groupedOffers[].offers[0].offerAbsoluteUri)
  function findUrl(o, depth = 0) {
    for (const k of ["offerAbsoluteUri", "offerUrl", "offerURL", "absoluteUri", "url", "link", "href"]) {
      if (offerId(o[k])) return str(o[k]);
    }
    if (depth >= 2) return "";
    for (const v of Object.values(o)) {
      if (Array.isArray(v)) { for (const x of v.slice(0, 5)) if (x && typeof x === "object") { const u = findUrl(x, depth + 1); if (u) return u; } }
      else if (v && typeof v === "object") { const u = findUrl(v, depth + 1); if (u) return u; }
    }
    return "";
  }

  function company(o) {
    return first(o.companyName, o.employerName, o.employer?.name, o.employer, o.hiringOrganization?.name,
      o.company?.name, o.company, o.offer?.companyName, o.offer?.employer?.name);
  }

  function title(o) {
    return first(o.jobTitle, o.positionName, o.offerTitle, o.position, o.title, o.offer?.jobTitle, o.offer?.title);
  }

  function asItem(o) {
    const t = title(o), c = company(o), url = findUrl(o);
    if (!t || !c || !url) return null;
    const sub = Array.isArray(o.offers) ? o.offers[0] || {} : {};
    return {
      id: offerId(url),
      url: cleanUrl(url),
      title: t,
      company: c,
      city: first(o.displayWorkplace, sub.displayWorkplace, o.city, o.jobLocation?.address?.addressLocality, o.workplace),
      workplace: list(o.workModes),
      experience: list(o.positionLevels),
      salary: first(o.salaryDisplayText, o.salary),
      published_at: /^\d{4}-\d{2}-\d{2}/.test(first(o.lastPublicated, o.publicationDate, o.datePosted))
        ? first(o.lastPublicated, o.publicationDate, o.datePosted) : "",
      applied_at: toDate(first(o.applicationDate, o.appliedAt, o.applicationSentDate, o.sentDate, o.applyDate,
        o.applicationCreatedAt, o.createdAt, o.date)),
    };
  }

  // przechodzi po wszystkich obiektach JSON-a; obiekt rozpoznany jako oferta nie jest przeszukiwany głębiej
  function fromJson(roots) {
    const out = new Map(), seen = new Set();
    const walk = (v, depth) => {
      if (!v || typeof v !== "object" || depth > 40 || seen.has(v)) return;
      seen.add(v);
      if (Array.isArray(v)) { v.forEach((x) => walk(x, depth + 1)); return; }
      const it = asItem(v);
      if (it) { if (!out.has(it.id)) out.set(it.id, it); return; }
      Object.values(v).forEach((x) => walk(x, depth + 1));
    };
    roots.forEach((r) => walk(r, 0));
    return [...out.values()];
  }

  return { offerId, cleanUrl, toDate, fromJson };
})();
if (typeof module !== "undefined") module.exports = globalThis.didijjitParse;
