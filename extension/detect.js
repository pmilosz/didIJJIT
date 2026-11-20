// Daje znać stronie programu didIJJIT (localhost), że wtyczka jest zainstalowana,
// i wysyła zapisy aplikacji, które czekały w kolejce, bo program był wyłączony.
document.documentElement.dataset.didijjitExtension = chrome.runtime.getManifest().version;
chrome.runtime.sendMessage({ type: "flush" }, (r) => {
  if (r?.sent) document.documentElement.dataset.didijjitFlushed = String(r.sent);
});
