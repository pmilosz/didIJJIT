// Pośrednik między stroną justjoin.it a lokalnym serwerem didIJJIT.
// Zapytania idą stąd, bo skrypt strony podlega CORS strony, a wtyczka ma uprawnienie do localhost.
const api = globalThis.browser ?? chrome;

// Zapisy aplikacji, których nie da się wysłać, bo program jest wyłączony, czekają w kolejce
// (storage.local przetrwa zamknięcie przeglądarki) i idą do programu przy najbliższym kontakcie.
const QUEUE = "pendingSaves";
const QUEUED_PATHS = ["/api/applied-from-page", "/api/pracuj/applications"];
const localDay = () => new Date().toLocaleDateString("sv-SE"); // RRRR-MM-DD w strefie użytkownika

async function baseUrl() {
  const { port } = await api.storage.local.get({ port: 8765 });
  return `http://localhost:${port}`;
}

async function post(base, path, body) {
  return fetch(base + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// data kliknięcia zapisana od razu — inaczej zaległa aplikacja dostałaby datę wysłania z kolejki
function withDate(path, body) {
  const day = localDay();
  if (path === "/api/applied-from-page") return { ...body, applied_at: body.applied_at || day };
  if (path === "/api/pracuj/applications") return { ...body, items: body.items.map((it) => ({ ...it, applied_at: it.applied_at || day })) };
  return body;
}

async function enqueue(path, body) {
  const { [QUEUE]: q } = await api.storage.local.get({ [QUEUE]: [] });
  q.push({ path, body: withDate(path, body) });
  await api.storage.local.set({ [QUEUE]: q });
  return q.length;
}

async function queueSize() {
  return (await api.storage.local.get({ [QUEUE]: [] }))[QUEUE].length;
}

let flushing = null;
function flush(base) {
  // jedno opróżnianie naraz, żeby ta sama aplikacja nie poszła dwa razy
  flushing ||= (async () => {
    try {
      const { [QUEUE]: q } = await api.storage.local.get({ [QUEUE]: [] });
      let sent = 0;
      for (const item of q) {
        try {
          const r = await post(base, item.path, item.body);
          if (!r.ok && r.status >= 500) break; // program ma kłopot — spróbujemy później
          sent++; // 2xx albo błąd danych (4xx), którego ponawianie nic nie da
        } catch {
          break; // program nadal wyłączony
        }
      }
      if (sent) {
        const { [QUEUE]: now } = await api.storage.local.get({ [QUEUE]: [] });
        await api.storage.local.set({ [QUEUE]: now.slice(sent) }); // w międzyczasie mogły dojść nowe
      }
      return sent;
    } finally {
      flushing = null;
    }
  })();
  return flushing;
}

// zapis aplikacji: od razu do programu, a gdy program nie odpowiada — do kolejki
async function save(base, path, body) {
  try {
    const r = await post(base, path, withDate(path, body));
    return { ok: r.ok, data: await r.json().catch(() => ({})) };
  } catch {
    return { ok: true, queued: await enqueue(path, body), data: {} };
  }
}

api.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    const base = await baseUrl();
    // każda rozmowa z programem to okazja, żeby wysłać zaległe zapisy
    if (msg.type !== "flush" && (await queueSize())) flush(base).catch(() => {});
    try {
      if (msg.type === "flush") {
        reply({ ok: true, sent: await flush(base), left: await queueSize() });
      } else if (msg.type === "lookup") {
        const q = new URLSearchParams({ url: msg.url, company: msg.company || "" });
        const r = await fetch(`${base}/api/lookup?${q}`);
        reply({ ok: r.ok, data: await r.json() });
      } else if (msg.type === "applied") {
        reply(await save(base, "/api/applied-from-page", { url: msg.url, company: msg.company, title: msg.title }));
      } else if (msg.type === "api" && typeof msg.path === "string" && msg.path.startsWith("/api/")) {
        if (msg.body !== undefined && QUEUED_PATHS.includes(msg.path.split("?")[0])) {
          reply(await save(base, msg.path, msg.body));
          return;
        }
        // ogólne zapytanie do programu (strony pracuj.pl); tylko ścieżki API programu
        const r = await fetch(base + msg.path, msg.body === undefined ? {} : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(msg.body),
        });
        reply({ ok: r.ok, data: await r.json().catch(() => ({})) });
      }
    } catch (e) {
      reply({ ok: false, offline: true, base });
    }
  })();
  return true; // odpowiedź asynchroniczna
});

// przeglądarka startuje — może program już działa
api.runtime.onStartup?.addListener(async () => flush(await baseUrl()).catch(() => {}));
