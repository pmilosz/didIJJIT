// Wspólne narzędzia wtyczki dla stron pracuj.pl: pasek didIJJIT i rozmowa z programem przez background.js.
globalThis.didijjit = (() => {
  const BAR_ID = "didijjit-bar";

  // wersja z callbackiem działa tak samo w Chromium i Firefoksie
  const send = (msg) => new Promise((res) => chrome.runtime.sendMessage(msg, (r) => res(r || { ok: false, offline: true })));
  // GET, gdy body nie podano; POST z JSON-em w przeciwnym razie
  const api = (path, body) => send({ type: "api", path, body });

  const day = (iso) => new Date(iso.length === 10 ? iso + "T12:00" : iso).toLocaleDateString("pl-PL");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function hide() { document.getElementById(BAR_ID)?.remove(); }

  function show(kind, html, actions = []) {
    let el = document.getElementById(BAR_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = BAR_ID;
      document.documentElement.appendChild(el);
    }
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
    return el;
  }

  // przycisk „Aplikuj” — także gdy kliknięto ikonę/napis w środku albo element z role="button"
  function applyButton(e) {
    for (const n of e.composedPath()) {
      if (!(n instanceof Element)) continue;
      if (n.id === BAR_ID) return null;
      if (!n.matches('a,button,[role="button"]')) continue;
      const label = `${n.innerText || n.textContent || ""} ${n.getAttribute("aria-label") || ""} ${n.title || ""}`;
      return /aplikuj|apply/i.test(label) ? n : null;
    }
    return null;
  }

  // pamięć między przeładowaniami strony (np. przejście do formularza aplikacji)
  const storage = {
    get: (k) => new Promise((res) => chrome.storage.local.get({ [k]: null }, (r) => res(r?.[k] ?? null))),
    set: (k, v) => new Promise((res) => chrome.storage.local.set({ [k]: v }, res)),
  };

  return { BAR_ID, send, api, day, esc, hide, show, applyButton, storage };
})();
