let pollInterval = null;
let currentToken = null;

async function initAuth() {
  try {
    const res = await fetch('/voduploader/api/auth/request', { method: 'POST' });
    const data = await res.json();
    if (data.token) {
      currentToken = data.token;
      const tgBtn = document.getElementById('tgLink');
      tgBtn.href = data.deep_link;
      document.getElementById('statusText').innerText = 'Warte auf Freigabe in Telegram...';
      startPolling(data.token);
    } else {
      document.getElementById('statusText').innerText = 'Fehler beim Abrufen des Tokens.';
    }
  } catch (err) {
    document.getElementById('statusText').innerText = 'Verbindung zum Server fehlgeschlagen.';
  }
}

function startPolling(token) {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/voduploader/api/auth/check?token=${token}`);
      const data = await res.json();
      if (data.status === 'approved') {
        clearInterval(pollInterval);
        document.getElementById('spinner').style.display = 'none';
        document.getElementById('statusBox').innerHTML = '<span class="success-badge">✅ Freigegeben! Weiterleitung...</span>';
        setTimeout(() => {
          window.location.href = '/voduploader/';
        }, 800);
      } else if (data.status === 'denied') {
        clearInterval(pollInterval);
        document.getElementById('spinner').style.display = 'none';
        document.getElementById('statusBox').innerHTML = '<span class="denied-badge">⛔ Zugriff verweigert</span>';
      }
    } catch (e) {}
  }, 1500);
}

initAuth();
