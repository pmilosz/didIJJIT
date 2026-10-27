// Pośrednik między stroną justjoin.it a lokalnym serwerem didIJJIT.
// Zapytania idą stąd, bo skrypt strony podlega CORS strony, a wtyczka ma uprawnienie do localhost.
const api = globalThis.browser ?? chrome;

async function baseUrl() {
  const { port } = await api.storage.local.get({ port: 8765 });
  return `http://localhost:${port}`;
}

api.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    const base = await baseUrl();
    try {
      if (msg.type === "lookup") {
        const q = new URLSearchParams({ url: msg.url, company: msg.company || "" });
        const r = await fetch(`${base}/api/lookup?${q}`);
        reply({ ok: r.ok, data: await r.json() });
      } else if (msg.type === "applied") {
        const r = await fetch(`${base}/api/applied-from-page`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: msg.url, company: msg.company, title: msg.title }),
        });
        reply({ ok: r.ok, data: await r.json() });
      }
    } catch (e) {
      reply({ ok: false, offline: true, base });
    }
  })();
  return true; // odpowiedź asynchroniczna
});
