const api = globalThis.browser ?? chrome;
const input = document.getElementById("port");
api.storage.local.get({ port: 8765 }).then(({ port }) => (input.value = port));
document.getElementById("save").onclick = async () => {
  await api.storage.local.set({ port: Number(input.value) || 8765 });
  document.getElementById("msg").textContent = "Zapisano.";
};
