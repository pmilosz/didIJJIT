// Daje znać stronie programu didIJJIT (localhost), że wtyczka jest zainstalowana.
document.documentElement.dataset.didijjitExtension = chrome.runtime.getManifest().version;
