"""
HTML and Client-Side UI Templates for the VOD Uploader Web Dashboard.
"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ripper VOD | Login</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(17, 24, 39, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --telegram: #229ed9;
      --telegram-hover: #1e87bb;
      --emerald: #10b981;
      --rose: #f43f5e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.12) 0px, transparent 50%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .login-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-radius: 20px;
      padding: 2.5rem 2rem;
      width: 100%;
      max-width: 440px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 40px rgba(99, 102, 241, 0.1);
      text-align: center;
    }
    .brand-icon {
      width: 64px;
      height: 64px;
      background: linear-gradient(135deg, #6366f1, #06b6d4);
      border-radius: 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 1.5rem;
      box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.4);
    }
    .brand-icon svg { width: 32px; height: 32px; fill: white; }
    h1 {
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 0.5rem;
      background: linear-gradient(to right, #ffffff, #cbd5e1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    p.desc {
      color: var(--text-muted);
      font-size: 0.92rem;
      line-height: 1.5;
      margin-bottom: 2rem;
    }
    .btn-tg {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.75rem;
      background: var(--telegram);
      color: white;
      text-decoration: none;
      font-weight: 600;
      font-size: 1rem;
      padding: 0.9rem 1.5rem;
      border-radius: 12px;
      transition: all 0.2s ease;
      box-shadow: 0 8px 20px -4px rgba(34, 158, 217, 0.4);
      cursor: pointer;
      border: none;
      width: 100%;
    }
    .btn-tg:hover {
      background: var(--telegram-hover);
      transform: translateY(-2px);
      box-shadow: 0 12px 25px -4px rgba(34, 158, 217, 0.5);
    }
    .btn-tg svg { width: 22px; height: 22px; fill: white; }
    .status-box {
      margin-top: 1.75rem;
      padding: 1rem;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 0.88rem;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.6rem;
      color: var(--text-muted);
    }
    .spinner {
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.2);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .success-badge { color: var(--emerald); font-weight: 600; }
    .denied-badge { color: var(--rose); font-weight: 600; }
    .info-footer {
      margin-top: 2rem;
      font-size: 0.8rem;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="login-card">
    <div class="brand-icon">
      <svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10.5 6l-5-3v6l5-3z"/></svg>
    </div>
    <h1>VOD Uploader Dashboard</h1>
    <p class="desc">Klicke auf den Button, um die Anmeldung direkt in Telegram freizugeben.</p>

    <a id="tgLink" href="#" target="_blank" class="btn-tg">
      <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.75-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .37z"/></svg>
      Mit Telegram bestätigen
    </a>

    <div class="status-box" id="statusBox">
      <div class="spinner" id="spinner"></div>
      <span id="statusText">Initialisiere Login-Token...</span>
    </div>

    <div class="info-footer">
      Nur autorisierte Konten (@Ripperchieff, @x42067) haben Zugriff.
    </div>
  </div>

  <script>
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
  </script>
</body>
</html>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ripper VOD | Live-Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #080c14;
      --card-bg: rgba(15, 23, 42, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-glow: rgba(99, 102, 241, 0.25);
      --cyan: #06b6d4;
      --emerald: #10b981;
      --amber: #f59e0b;
      --rose: #f43f5e;
      --border-radius: 16px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 40%),
        radial-gradient(at 100% 0%, rgba(6, 182, 212, 0.08) 0px, transparent 40%);
      color: var(--text);
      min-height: 100vh;
      padding: 1.5rem;
    }
    .container {
      max-width: 1280px;
      margin: 0 auto;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 2rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--card-border);
      flex-wrap: wrap;
      gap: 1rem;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.9rem;
    }
    .brand-logo {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, #6366f1, #06b6d4);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 15px rgba(99, 102, 241, 0.35);
    }
    .brand-logo svg { width: 24px; height: 24px; fill: white; }
    .brand-title {
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .brand-subtitle {
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .header-right {
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    .user-pill {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--card-border);
      padding: 0.4rem 0.9rem;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 500;
    }
    .user-pill .dot {
      width: 8px;
      height: 8px;
      background: var(--emerald);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--emerald);
    }
    .btn-logout {
      background: transparent;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 0.45rem 0.9rem;
      border-radius: 10px;
      font-size: 0.82rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-logout:hover {
      background: rgba(244, 63, 94, 0.15);
      color: var(--rose);
      border-color: rgba(244, 63, 94, 0.3);
    }
    .btn-nav {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: #c7d2fe;
      padding: 0.45rem 0.9rem;
      border-radius: 10px;
      font-size: 0.82rem;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.2s;
    }
    .btn-nav:hover {
      background: rgba(99, 102, 241, 0.22);
      border-color: rgba(99, 102, 241, 0.5);
      color: #e0e7ff;
    }

    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      backdrop-filter: blur(12px);
      border-radius: var(--border-radius);
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
    }
    .stat-label {
      font-size: 0.8rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 600;
    }
    .stat-value {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text);
    }

    /* RSS archive */
    .rss-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 1rem;
      margin-bottom: 1rem;
    }
    .rss-feed-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.55rem 0.75rem;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid rgba(255, 255, 255, 0.04);
      font-size: 0.86rem;
    }
    .rss-feed-row + .rss-feed-row { margin-top: 0.4rem; }
    .rss-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
      flex: 0 0 auto;
    }
    .rss-dot-ok { background: var(--emerald); }
    .rss-dot-error { background: var(--rose); }
    .rss-dot-idle { background: #64748b; }

    /* Main Dashboard Grid */
    .dash-grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 1.5rem;
      margin-bottom: 2rem;
    }
    @media (max-width: 960px) {
      .dash-grid { grid-template-columns: 1fr; }
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      backdrop-filter: blur(16px);
      border-radius: var(--border-radius);
      padding: 1.5rem;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    }
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1.25rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .card-title {
      font-size: 1.05rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .badge {
      font-size: 0.75rem;
      padding: 0.25rem 0.6rem;
      border-radius: 6px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-live {
      background: rgba(99, 102, 241, 0.2);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.4);
      animation: pulse 2s infinite;
    }
    .badge-idle {
      background: rgba(148, 163, 184, 0.1);
      color: var(--text-muted);
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    /* Active Job Box */
    .active-job {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }
    .job-meta {
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    .streamer-avatar {
      width: 52px;
      height: 52px;
      background: linear-gradient(135deg, #1e293b, #334155);
      border-radius: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.4rem;
      font-weight: 700;
      color: #e2e8f0;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .job-details h3 {
      font-size: 1.15rem;
      font-weight: 600;
      margin-bottom: 0.25rem;
    }
    .job-details .sub {
      font-size: 0.85rem;
      color: var(--text-muted);
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    /* Progress Bar */
    .progress-section {
      background: rgba(0, 0, 0, 0.25);
      border-radius: 12px;
      padding: 1.2rem;
      border: 1px solid rgba(255, 255, 255, 0.04);
    }
    .progress-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.75rem;
      font-size: 0.9rem;
    }
    .progress-stage {
      font-weight: 600;
      color: #e2e8f0;
    }
    .progress-pct {
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--primary);
    }
    .bar-bg {
      width: 100%;
      height: 12px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 6px;
      overflow: hidden;
      margin-bottom: 0.75rem;
      position: relative;
    }
    .bar-fill {
      height: 100%;
      background: linear-gradient(90deg, #6366f1, #06b6d4, #10b981);
      background-size: 200% 100%;
      animation: gradientMove 3s linear infinite;
      border-radius: 6px;
      width: 0%;
      transition: width 0.4s ease;
    }
    @keyframes gradientMove {
      0% { background-position: 100% 0; }
      100% { background-position: -100% 0; }
    }
    .progress-footer {
      display: flex;
      justify-content: space-between;
      font-size: 0.82rem;
      color: var(--text-muted);
    }

    /* Queue List */
    .queue-list {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      max-height: 280px;
      overflow-y: auto;
    }
    .queue-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem 1rem;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 10px;
      font-size: 0.88rem;
    }
    .queue-item .left {
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
    }
    .queue-item .streamer-name {
      font-weight: 600;
      color: #e2e8f0;
    }
    .queue-item .queued-title {
      font-size: 0.78rem;
      color: var(--text-muted);
    }
    .queue-pos {
      font-size: 0.8rem;
      color: var(--primary);
      font-weight: 700;
      background: rgba(99, 102, 241, 0.15);
      padding: 0.2rem 0.55rem;
      border-radius: 6px;
    }

    /* History Table */
    .history-card {
      margin-bottom: 2rem;
    }
    .table-wrap {
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
      text-align: left;
    }
    th {
      padding: 0.75rem 1rem;
      color: var(--text-muted);
      font-weight: 600;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    td {
      padding: 0.85rem 1rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: #cbd5e1;
    }
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    .topic-link {
      color: var(--cyan);
      text-decoration: none;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }
    .topic-link:hover {
      text-decoration: underline;
    }

    /* Live Log Console */
    .logs-console {
      background: #050811;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 1rem;
      font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
      font-size: 0.8rem;
      line-height: 1.6;
      max-height: 250px;
      overflow-y: auto;
      color: #94a3b8;
    }
    .log-line {
      display: flex;
      gap: 0.75rem;
      word-break: break-word;
    }
    .log-time { color: #64748b; flex-shrink: 0; }
    .log-info { color: #38bdf8; }
    .log-warning { color: #f59e0b; }
    .log-error { color: #f43f5e; font-weight: 600; }

    .empty-state {
      padding: 2.5rem;
      text-align: center;
      color: var(--text-muted);
      font-size: 0.95rem;
    }
    .empty-state svg {
      width: 48px;
      height: 48px;
      fill: #475569;
      margin-bottom: 0.75rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10.5 6l-5-3v6l5-3z"/></svg>
        </div>
        <div>
          <div class="brand-title">Ripper VOD Uploader</div>
          <div class="brand-subtitle">Automatisches Telegram Topic-Archiv</div>
        </div>
      </div>
      <div class="header-right">
        <div class="user-pill">
          <div class="dot"></div>
          <span id="userName">Autorisiert</span>
        </div>
        <a class="btn-nav" href="/voduploader/topics">Topics verwalten</a>
        <button class="btn-logout" onclick="logout()">Abmelden</button>
      </div>
    </header>

    <!-- Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Bot Status</div>
        <div class="stat-value" id="botStatus" style="color: var(--emerald);">Online</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Warteschlange</div>
        <div class="stat-value" id="queueCount">0 Jobs</div>
      </div>
      <a class="stat-card" href="/voduploader/topics" style="text-decoration: none; color: inherit;">
        <div class="stat-label">Topics gemappt</div>
        <div class="stat-value" id="topicCount">-</div>
      </a>
      <div class="stat-card">
        <div class="stat-label">Ziel-Forum</div>
        <div class="stat-value" style="font-size: 1.15rem; color: #a5b4fc;">Ripper Archiv</div>
      </div>
    </div>

    <!-- RSS Archive -->
    <div class="card" style="margin-bottom: 2rem;">
      <div class="card-header">
        <div class="card-title">
          <span>RSS-Archiv (rss.app)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
          <span class="badge badge-idle" id="rssBadge">–</span>
          <button class="btn-logout" id="rssBackfillBtn" onclick="triggerRssBackfill()">10 nachholen</button>
          <button class="btn-logout" id="rssBtn" onclick="triggerRss()">Jetzt prüfen</button>
        </div>
      </div>
      <div class="rss-grid">
        <div>
          <div class="stat-label">Feeds</div>
          <div class="stat-value" id="rssFeeds">-</div>
        </div>
        <div>
          <div class="stat-label">Archiviert</div>
          <div class="stat-value" id="rssArchived" style="color: var(--emerald);">0</div>
        </div>
        <div>
          <div class="stat-label">Übersprungen</div>
          <div class="stat-value" id="rssSkipped">0</div>
        </div>
        <div>
          <div class="stat-label" title="Retry, Live-Warteschlange und endgültige Fehler">Wartet / Fehler</div>
          <div class="stat-value" id="rssFailed" style="color: var(--rose);">0</div>
        </div>
        <div>
          <div class="stat-label">Letzter Lauf</div>
          <div class="stat-value" id="rssLastRun" style="font-size: 1rem;">-</div>
        </div>
      </div>
      <div id="rssFeedList"></div>
    </div>

    <!-- n8n Workflows -->
    <div class="card" id="n8nCard" style="margin-bottom: 2rem; display: none;">
      <div class="card-header">
        <div class="card-title">
          <span>n8n-Workflows</span>
        </div>
        <div id="n8nButtons" style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;"></div>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted);">
        Startet den Streamrecorder-Workflow des jeweiligen Accounts sofort – zusätzlich zum 15-Minuten-Intervall.
      </div>
    </div>

    <!-- Active + Queue Grid -->
    <div class="dash-grid">
      <!-- Active Job Card -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <span>Aktiver Upload</span>
          </div>
          <span class="badge" id="activeBadge">IDLE</span>
        </div>

        <div id="activeJobContainer">
          <div class="empty-state">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
            <div>Aktuell kein aktiver Upload in Bearbeitung.</div>
            <div style="font-size: 0.8rem; margin-top: 0.25rem;">Der Bot wartet auf neue Requests von n8n.</div>
          </div>
        </div>
      </div>

      <!-- Queue Card -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <span>Warteschlange</span>
          </div>
          <span class="badge badge-idle" id="queueBadge">0 wartend</span>
        </div>
        <div class="queue-list" id="queueList">
          <div class="empty-state" style="padding: 1.5rem;">
            Keine wartenden VODs.
          </div>
        </div>
      </div>
    </div>

    <!-- History Card -->
    <div class="card history-card">
      <div class="card-header">
        <div class="card-title">
          <span>Kürzlich archivierte VODs</span>
        </div>
        <span style="font-size: 0.82rem; color: var(--text-muted);" id="historyCount">0 abgeschlossen</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Zeitstempel</th>
              <th>Streamer</th>
              <th>Titel</th>
              <th>Dateien / Größe</th>
              <th>Ziel-Topic</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="historyTableBody">
            <tr>
              <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">Noch keine VODs in dieser Session hochgeladen.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Live Logs -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">
          <span>Live-Log-Konsole</span>
        </div>
        <span style="font-size: 0.8rem; color: var(--text-muted);">Echtzeit-Meldungen</span>
      </div>
      <div class="logs-console" id="logsConsole">
        <div style="color: #64748b;">Verbinde mit Live-Log Stream...</div>
      </div>
    </div>
  </div>

  <script>
    let sseSource = null;

    function renderActiveJob(job) {
      const container = document.getElementById('activeJobContainer');
      const badge = document.getElementById('activeBadge');

      if (!job) {
        badge.className = 'badge badge-idle';
        badge.innerText = 'IDLE';
        container.innerHTML = `
          <div class="empty-state">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
            <div>Aktuell kein aktiver Upload in Bearbeitung.</div>
            <div style="font-size: 0.8rem; margin-top: 0.25rem;">Der Bot wartet auf neue Aufnahmen.</div>
          </div>
        `;
        return;
      }

      badge.className = 'badge badge-live';
      badge.innerText = 'AKTIV';

      const streamerInitial = (job.streamer || '?').charAt(0).toUpperCase();
      const pct = job.pct || 0;
      const doneMb = Math.round((job.bytes_done || 0) / (1024 * 1024));
      const totalMb = Math.round((job.bytes_total || 0) / (1024 * 1024));
      const speed = job.speed_mbps ? `${job.speed_mbps.toFixed(1)} MB/s` : '';
      const eta = job.eta_seconds ? `${Math.round(job.eta_seconds)}s Rest` : '';

      container.innerHTML = `
        <div class="active-job">
          <div class="job-meta">
            <div class="streamer-avatar">${streamerInitial}</div>
            <div class="job-details">
              <h3>${escapeHtml(job.streamer || 'Unbekannt')}</h3>
              <div class="sub">
                <span>📌 ${escapeHtml(job.title || 'Kein Titel')}</span>
                <span>•</span>
                <span>ID: <code>${escapeHtml(job.job_id || '')}</code></span>
              </div>
            </div>
          </div>

          <div class="progress-section">
            <div class="progress-header">
              <span class="progress-stage">${escapeHtml(job.stage_label || 'In Bearbeitung...')}</span>
              <span class="progress-pct">${pct}%</span>
            </div>
            <div class="bar-bg">
              <div class="bar-fill" style="width: ${pct}%"></div>
            </div>
            <div class="progress-footer">
              <span>${doneMb} / ${totalMb > 0 ? totalMb + ' MB' : '...'}</span>
              <span>${[speed, eta].filter(Boolean).join(' • ')}</span>
            </div>
          </div>
        </div>
      `;
    }

    function renderQueue(queue) {
      const list = document.getElementById('queueList');
      const badge = document.getElementById('queueBadge');
      badge.innerText = `${queue.length} wartend`;

      if (!queue || queue.length === 0) {
        list.innerHTML = '<div class="empty-state" style="padding: 1.5rem;">Keine wartenden VODs.</div>';
        return;
      }

      list.innerHTML = queue.map((item, idx) => `
        <div class="queue-item">
          <div class="left">
            <div class="streamer-name">${escapeHtml(item.streamer || 'Unbekannt')}</div>
            <div class="queued-title">${escapeHtml(item.title || 'Kein Titel')}</div>
          </div>
          <div class="queue-pos">#${idx + 1}</div>
        </div>
      `).join('');
    }

    function renderHistory(history) {
      const tbody = document.getElementById('historyTableBody');
      const count = document.getElementById('historyCount');
      count.innerText = `${history.length} archiviert`;

      if (!history || history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">Noch keine VODs in dieser Session hochgeladen.</td></tr>';
        return;
      }

      tbody.innerHTML = history.map(item => {
        const isSuccess = item.status === 'success';
        const statusBadge = isSuccess 
          ? '<span style="color: var(--emerald); font-weight: 600;">✓ Fertig</span>'
          : '<span style="color: var(--rose); font-weight: 600;">✗ Fehler</span>';

        const topicCell = item.topic_id
          ? `<a class="topic-link" href="https://t.me/RippersArchiv/${item.topic_id}" target="_blank">💬 ${escapeHtml(item.topic_name || ('Topic #' + item.topic_id))}</a>`
          : '<span style="color: var(--text-muted);">-</span>';

        return `
          <tr>
            <td style="color: var(--text-muted);">${escapeHtml(item.finished_at || '')}</td>
            <td style="font-weight: 600; color: #f1f5f9;">${escapeHtml(item.streamer || '')}</td>
            <td>${escapeHtml(item.title || '')}</td>
            <td>${item.parts || 1} Teil(e) (${item.total_size_mb || '?'} MB)</td>
            <td>${topicCell}</td>
            <td>${statusBadge}</td>
          </tr>
        `;
      }).join('');
    }

    function renderLogs(logs) {
      const consoleEl = document.getElementById('logsConsole');
      if (!logs || logs.length === 0) return;

      consoleEl.innerHTML = logs.map(line => {
        let lvlClass = 'log-info';
        if (line.level === 'WARNING') lvlClass = 'log-warning';
        if (line.level === 'ERROR') lvlClass = 'log-error';
        return `
          <div class="log-line">
            <span class="log-time">${escapeHtml(line.time || '')}</span>
            <span class="${lvlClass}">[${escapeHtml(line.level || 'INFO')}]</span>
            <span>${escapeHtml(line.message || '')}</span>
          </div>
        `;
      }).join('');
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    function formatTs(ts) {
      if (!ts) return '-';
      const d = new Date(ts * 1000);
      return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function renderRss(rss) {
      if (!rss) return;
      const counts = rss.counts || {};
      const feeds = rss.feeds || [];
      const badge = document.getElementById('rssBadge');

      document.getElementById('rssFeeds').innerText = feeds.length;
      document.getElementById('rssArchived').innerText = counts.archived || 0;
      document.getElementById('rssSkipped').innerText = counts.skipped || 0;
      document.getElementById('rssFailed').innerText = (counts.failed || 0) + (counts.retry || 0) + (counts.live || 0);
      document.getElementById('rssLastRun').innerText = formatTs(rss.last_poll_finished);

      if (!rss.enabled) {
        badge.className = 'badge badge-idle';
        badge.innerText = 'AUS';
      } else if (rss.running) {
        badge.className = 'badge badge-live';
        badge.innerText = 'LÄUFT';
      } else if (rss.last_error) {
        badge.className = 'badge badge-idle';
        badge.innerText = 'FEHLER';
      } else {
        badge.className = 'badge badge-idle';
        badge.innerText = 'BEREIT';
      }

      const list = document.getElementById('rssFeedList');
      if (!feeds.length) {
        list.innerHTML = '<div class="empty-state" style="padding: 1rem;">Keine RSS-Feeds geladen – bitte RSS_FEED_URLS bzw. OPML-Quelle prüfen.</div>';
        return;
      }

      list.innerHTML = feeds.map(feed => {
        const dot = feed.error ? 'rss-dot-error' : (feed.last_check ? 'rss-dot-ok' : 'rss-dot-idle');
        const info = feed.error
          ? escapeHtml(feed.error)
          : `${feed.items || 0} Items${feed.last_check ? ' • ' + formatTs(feed.last_check) : ''}`;
        return `
          <div class="rss-feed-row">
            <div style="display: flex; align-items: center; gap: 0.5rem; min-width: 0;">
              <span class="rss-dot ${dot}"></span>
              <span style="font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(feed.title)}</span>
              ${feed.bundle ? '<span style="font-size: 0.7rem; color: var(--text-muted);">BUNDLE</span>' : ''}
            </div>
            <span style="color: var(--text-muted); font-size: 0.78rem; text-align: right;">${info}</span>
          </div>
        `;
      }).join('');
    }

    async function triggerRss() {
      const btn = document.getElementById('rssBtn');
      btn.disabled = true;
      btn.innerText = 'Startet...';
      let label = 'Jetzt prüfen';
      try {
        const res = await fetch('/voduploader/rss/check', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) label = 'Gestartet';
        else if (data.status === 'busy') label = 'Läuft bereits';
        else label = 'Nicht verfügbar';
      } catch (e) {
        label = 'Fehler';
      }
      btn.innerText = label;
      setTimeout(() => {
        btn.disabled = false;
        btn.innerText = 'Jetzt prüfen';
      }, 4000);
    }

    async function triggerRssBackfill() {
      const btn = document.getElementById('rssBackfillBtn');
      btn.disabled = true;
      btn.innerText = 'Startet...';
      let label = '10 nachholen';
      try {
        const res = await fetch('/voduploader/rss/backfill?limit=10', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) label = 'Gestartet';
        else if (data.status === 'busy') label = 'Läuft bereits';
        else label = 'Nicht verfügbar';
      } catch (e) {
        label = 'Fehler';
      }
      btn.innerText = label;
      setTimeout(() => {
        btn.disabled = false;
        btn.innerText = '10 nachholen';
      }, 4000);
    }

    const N8N_LABELS = {
      karbfenchieff: 'Karbfen',
      karpfenchieff: 'Karpfen',
      ripperchieff: 'Ripper'
    };
    let n8nButtonsRendered = false;

    function renderN8nButtons(names) {
      if (n8nButtonsRendered || !Array.isArray(names) || names.length === 0) return;
      const box = document.getElementById('n8nButtons');
      if (!box) return;
      box.innerHTML = names.map(function(name) {
        const label = N8N_LABELS[name] || name;
        return `<button class="btn-logout" id="n8nBtn_${escapeHtml(name)}" title="n8n-Workflow ${escapeHtml(label)} starten" onclick="triggerN8n('${escapeHtml(name)}', this)">${escapeHtml(label)}</button>`;
      }).join('');
      const card = document.getElementById('n8nCard');
      if (card) card.style.display = 'block';
      n8nButtonsRendered = true;
    }

    async function triggerN8n(name, btn) {
      const original = btn.innerText;
      btn.disabled = true;
      btn.innerText = 'Startet...';
      let label = 'Gestartet';
      try {
        const res = await fetch(`/voduploader/n8n/run?name=${encodeURIComponent(name)}`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (res.ok) label = 'Gestartet';
        else if (res.status === 429) label = 'Zu schnell';
        else if (res.status === 401) label = 'Login';
        else if (data.status === 'disabled') label = 'Nicht verfügbar';
        else label = 'Fehler';
      } catch (e) {
        label = 'Fehler';
      }
      btn.innerText = label;
      setTimeout(() => {
        btn.disabled = false;
        btn.innerText = original;
      }, 4000);
    }

    function connectSSE() {
      if (sseSource) sseSource.close();
      sseSource = new EventSource('/voduploader/api/events');

      sseSource.onmessage = function(e) {
        try {
          const data = JSON.parse(e.data);
          if (data.user) document.getElementById('userName').innerText = data.user;
          if (data.queue_count !== undefined) document.getElementById('queueCount').innerText = `${data.queue_count} Jobs`;
          if (data.topic_count !== undefined) document.getElementById('topicCount').innerText = `${data.topic_count} Topics`;
          if (data.active_job !== undefined) renderActiveJob(data.active_job);
          if (data.queue !== undefined) renderQueue(data.queue);
          if (data.history !== undefined) renderHistory(data.history);
          if (data.logs !== undefined) renderLogs(data.logs);
          if (data.rss !== undefined) renderRss(data.rss);
          if (data.n8n_workflows !== undefined) renderN8nButtons(data.n8n_workflows);
        } catch (err) {}
      };

      sseSource.onerror = function() {
        sseSource.close();
        setTimeout(connectSSE, 3000);
      };
    }

    async function initialFetch() {
      try {
        const res = await fetch('/voduploader/api/status');
        if (res.status === 401) {
          window.location.href = '/voduploader';
          return;
        }
        const data = await res.json();
        if (data.user) document.getElementById('userName').innerText = data.user;
        if (data.queue_count !== undefined) document.getElementById('queueCount').innerText = `${data.queue_count} Jobs`;
        if (data.topic_count !== undefined) document.getElementById('topicCount').innerText = `${data.topic_count} Topics`;
        renderActiveJob(data.active_job);
        renderQueue(data.queue);
        renderHistory(data.history);
        renderLogs(data.logs);
        if (data.rss !== undefined) renderRss(data.rss);
        if (data.n8n_workflows !== undefined) renderN8nButtons(data.n8n_workflows);
      } catch (e) {}
    }

    async function logout() {
      try {
        await fetch('/voduploader/api/logout', { method: 'POST' });
      } catch (e) {}
      window.location.href = '/voduploader';
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/[&<>"']/g, function(m) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[m];
      });
    }

    initialFetch();
    connectSSE();
  </script>
</body>
</html>
"""

TOPICS_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ripper VOD | Topic-Verwaltung</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #080c14;
      --card-bg: rgba(15, 23, 42, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-glow: rgba(99, 102, 241, 0.25);
      --cyan: #06b6d4;
      --emerald: #10b981;
      --amber: #f59e0b;
      --rose: #f43f5e;
      --border-radius: 16px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    [hidden] { display: none !important; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      background-image:
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 40%),
        radial-gradient(at 100% 0%, rgba(6, 182, 212, 0.08) 0px, transparent 40%);
      color: var(--text);
      min-height: 100vh;
      padding: 1.5rem;
    }
    .container { max-width: 1280px; margin: 0 auto; }
    header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 1.5rem; padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--card-border); flex-wrap: wrap; gap: 1rem;
    }
    .brand { display: flex; align-items: center; gap: 0.9rem; }
    .brand-logo {
      width: 44px; height: 44px; border-radius: 12px;
      background: linear-gradient(135deg, #6366f1, #06b6d4);
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 4px 15px rgba(99, 102, 241, 0.35);
    }
    .brand-logo svg { width: 24px; height: 24px; fill: white; }
    .brand-title { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; }
    .brand-subtitle { font-size: 0.8rem; color: var(--text-muted); }
    .header-right { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
    .user-pill {
      display: flex; align-items: center; gap: 0.5rem;
      background: rgba(255, 255, 255, 0.05); border: 1px solid var(--card-border);
      padding: 0.4rem 0.9rem; border-radius: 20px; font-size: 0.85rem; font-weight: 500;
    }
    .user-pill .dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: var(--emerald); box-shadow: 0 0 8px var(--emerald);
    }
    .btn-nav, .btn-logout, .btn-primary, .btn-ghost {
      display: inline-flex; align-items: center; justify-content: center; gap: 0.35rem;
      padding: 0.45rem 0.9rem; border-radius: 10px; font-size: 0.82rem;
      font-weight: 600; cursor: pointer; text-decoration: none; transition: all 0.2s;
      font-family: inherit;
    }
    .btn-nav {
      background: rgba(99, 102, 241, 0.12); border: 1px solid rgba(99, 102, 241, 0.3);
      color: #c7d2fe;
    }
    .btn-nav:hover { background: rgba(99, 102, 241, 0.22); color: #e0e7ff; }
    .btn-logout, .btn-ghost {
      background: transparent; border: 1px solid var(--card-border); color: var(--text-muted);
    }
    .btn-logout:hover {
      background: rgba(244, 63, 94, 0.15); color: var(--rose);
      border-color: rgba(244, 63, 94, 0.3);
    }
    .btn-ghost:hover { background: rgba(255, 255, 255, 0.05); color: var(--text); }
    .btn-primary {
      background: linear-gradient(135deg, #6366f1, #4f46e5);
      border: 1px solid rgba(99, 102, 241, 0.6); color: white;
      box-shadow: 0 6px 18px -6px rgba(99, 102, 241, 0.7);
    }
    .btn-primary:hover { filter: brightness(1.08); transform: translateY(-1px); }
    .btn-primary:disabled, .btn-ghost:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

    .page-title { margin-bottom: 0.35rem; font-size: 1.55rem; letter-spacing: -0.02em; }
    .page-desc { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 1.5rem; line-height: 1.5; }

    .card {
      background: var(--card-bg); border: 1px solid var(--card-border);
      backdrop-filter: blur(16px); border-radius: var(--border-radius);
      padding: 1.5rem; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
      margin-bottom: 1.5rem;
    }
    .card-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 1.1rem; padding-bottom: 0.75rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      gap: 1rem; flex-wrap: wrap;
    }
    .card-title { font-size: 1.05rem; font-weight: 600; }
    .muted { color: var(--text-muted); font-size: 0.82rem; }

    .add-grid {
      display: grid;
      grid-template-columns: minmax(180px, 2fr) minmax(130px, 1fr) auto auto;
      gap: 0.75rem; align-items: end;
    }
    @media (max-width: 860px) { .add-grid { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 560px) { .add-grid { grid-template-columns: 1fr; } }
    .field { display: flex; flex-direction: column; gap: 0.35rem; min-width: 0; }
    .field label {
      font-size: 0.72rem; color: var(--text-muted); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em;
    }
    input[type="text"], input[type="number"], select {
      width: 100%; background: rgba(2, 6, 23, 0.55);
      border: 1px solid rgba(255, 255, 255, 0.1); color: var(--text);
      border-radius: 10px; padding: 0.62rem 0.8rem; font-size: 0.88rem;
      font-family: inherit; outline: none; transition: border-color 0.2s, box-shadow 0.2s;
    }
    input:focus, select:focus {
      border-color: rgba(99, 102, 241, 0.7);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
    }
    input:disabled { opacity: 0.45; }
    .check-row {
      display: flex; align-items: center; gap: 0.5rem; font-size: 0.82rem;
      color: var(--text-muted); user-select: none; padding-bottom: 0.62rem;
    }
    .check-row input { accent-color: var(--primary); width: 16px; height: 16px; }
    .form-hint { color: var(--text-muted); font-size: 0.78rem; margin-top: 0.75rem; }

    .table-tools { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
    .search-box { position: relative; }
    .search-box input { min-width: 230px; padding-left: 2rem; }
    .search-box::before {
      content: '⌕'; position: absolute; left: 0.7rem; top: 50%;
      transform: translateY(-50%); color: var(--text-muted); font-size: 1rem;
    }
    .summary { color: var(--text-muted); font-size: 0.82rem; margin-bottom: 0.75rem; }

    .table-wrap { overflow-x: auto; border-radius: 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left; }
    th {
      padding: 0.7rem 0.9rem; color: var(--text-muted); font-weight: 600;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
      white-space: nowrap;
    }
    td {
      padding: 0.8rem 0.9rem; border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: #cbd5e1; vertical-align: middle;
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .topic-name { font-weight: 600; color: #f1f5f9; word-break: break-word; }
    .topic-id {
      display: inline-block; font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: 0.8rem; color: #a5b4fc; background: rgba(99, 102, 241, 0.14);
      padding: 0.15rem 0.5rem; border-radius: 6px; white-space: nowrap;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 0.3rem; max-width: 420px; }
    .chip {
      font-size: 0.72rem; color: #cbd5e1; background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 20px;
      padding: 0.15rem 0.55rem; white-space: nowrap;
    }
    .chip-more { color: var(--text-muted); }
    .row-actions { display: flex; gap: 0.4rem; flex-wrap: wrap; justify-content: flex-end; }
    .btn-small {
      padding: 0.3rem 0.6rem; border-radius: 7px; font-size: 0.75rem; font-weight: 600;
      border: 1px solid var(--card-border); background: rgba(255, 255, 255, 0.04);
      color: #cbd5e1; cursor: pointer; text-decoration: none; transition: all 0.2s;
      font-family: inherit; white-space: nowrap;
    }
    .btn-small:hover { background: rgba(255, 255, 255, 0.09); color: var(--text); }
    .btn-small.danger:hover {
      background: rgba(244, 63, 94, 0.15); color: #fda4af;
      border-color: rgba(244, 63, 94, 0.35);
    }
    .empty-state { padding: 2.5rem 1rem; text-align: center; color: var(--text-muted); font-size: 0.92rem; }
    .empty-state strong { display: block; color: #cbd5e1; margin-bottom: 0.25rem; }

    .modal-backdrop {
      position: fixed; inset: 0; background: rgba(2, 6, 23, 0.75);
      backdrop-filter: blur(4px); display: flex; align-items: center;
      justify-content: center; padding: 1rem; z-index: 50;
    }
    .modal {
      background: #0f172a; border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: var(--border-radius); padding: 1.5rem; width: 100%;
      max-width: 560px; max-height: 90vh; overflow-y: auto;
      box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6);
    }
    .modal-header {
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 1rem; margin-bottom: 1.1rem;
    }
    .modal-title { font-size: 1.1rem; font-weight: 700; }
    .modal-sub { color: var(--text-muted); font-size: 0.82rem; margin-top: 0.25rem; }
    .modal-section { margin-top: 1.2rem; }
    .modal-section > label {
      display: block; font-size: 0.72rem; color: var(--text-muted); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.5rem;
    }
    .alias-list { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.7rem; }
    .alias-row {
      display: inline-flex; align-items: center; gap: 0.35rem;
      background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 20px; padding: 0.2rem 0.35rem 0.2rem 0.65rem; font-size: 0.78rem;
    }
    .alias-row button {
      border: none; background: rgba(244, 63, 94, 0.15); color: #fda4af;
      width: 20px; height: 20px; border-radius: 50%; cursor: pointer;
      font-size: 0.85rem; line-height: 1; display: inline-flex;
      align-items: center; justify-content: center;
    }
    .alias-row button:hover { background: rgba(244, 63, 94, 0.3); }
    .inline-form { display: flex; gap: 0.5rem; }
    .inline-form input { flex: 1; }
    .modal-footer {
      display: flex; justify-content: flex-end; gap: 0.6rem;
      margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid rgba(255, 255, 255, 0.07);
    }

    .toast {
      position: fixed; right: 1.25rem; bottom: 1.25rem; z-index: 100;
      background: #0f172a; border: 1px solid rgba(255, 255, 255, 0.12);
      border-left: 4px solid var(--emerald); color: var(--text);
      padding: 0.85rem 1.1rem; border-radius: 10px; font-size: 0.86rem;
      box-shadow: 0 15px 40px rgba(0, 0, 0, 0.5); max-width: 380px;
      opacity: 0; transform: translateY(10px); pointer-events: none;
      transition: all 0.25s ease;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast.error { border-left-color: var(--rose); }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24"><path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10.5 6l-5-3v6l5-3z"/></svg>
        </div>
        <div>
          <div class="brand-title">Topic-Verwaltung</div>
          <div class="brand-subtitle">Aliase und Telegram-Topic-IDs verwalten</div>
        </div>
      </div>
      <div class="header-right">
        <div class="user-pill">
          <div class="dot"></div>
          <span id="userName">Autorisiert</span>
        </div>
        <a class="btn-nav" href="/voduploader">← Dashboard</a>
        <button class="btn-logout" onclick="logout()">Abmelden</button>
      </div>
    </header>

    <h1 class="page-title">Topics</h1>
    <p class="page-desc">
      Hier wird festgelegt, in welches Telegram-Forum-Topic ein Streamer bzw. Kanal einsortiert wird.
      Der Name ist ein Alias für die Topic-ID. Änderungen werden sofort in <code>topics_cache.json</code> gespeichert.
    </p>

    <!-- Add topic -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Topic hinzufügen</div>
        <div class="muted" id="chatInfo"></div>
      </div>
      <form id="addForm">
        <div class="add-grid">
          <div class="field">
            <label for="newName">Name / Alias</label>
            <input type="text" id="newName" maxlength="128" placeholder="z. B. MontanaBlack" autocomplete="off" required>
          </div>
          <div class="field">
            <label for="newTopicId">Topic-ID</label>
            <input type="text" id="newTopicId" inputmode="numeric" placeholder="z. B. 1234" autocomplete="off">
          </div>
          <label class="check-row" for="newCreate">
            <input type="checkbox" id="newCreate">
            Im Telegram-Forum erstellen
          </label>
          <button class="btn-primary" type="submit" id="addBtn">Hinzufügen</button>
        </div>
        <div class="form-hint">
          Entweder eine bestehende Topic-ID eintragen oder „Im Telegram-Forum erstellen“ aktivieren,
          damit der Bot ein neues Forum-Topic anlegt.
        </div>
      </form>
    </div>

    <!-- Topic table -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Gemappte Topics</div>
        <div class="table-tools">
          <div class="field" id="chatSelectWrap" hidden>
            <select id="chatSelect" onchange="onChatChange()"></select>
          </div>
          <div class="search-box">
            <input type="text" id="searchInput" placeholder="Suchen…" autocomplete="off" oninput="renderTopics()">
          </div>
          <button class="btn-ghost" type="button" onclick="loadTopics()">Aktualisieren</button>
        </div>
      </div>
      <div class="summary" id="summary">Lade Topics…</div>
      <div class="table-wrap" id="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Topic</th>
              <th>Topic-ID</th>
              <th>Aliase</th>
              <th style="text-align: right;">Aktionen</th>
            </tr>
          </thead>
          <tbody id="topicsBody"></tbody>
        </table>
      </div>
      <div class="empty-state" id="emptyState" hidden>
        <strong>Keine Topics gefunden</strong>
        <span id="emptyHint">Füge oben ein Topic hinzu.</span>
      </div>
    </div>
  </div>

  <!-- Edit modal -->
  <div class="modal-backdrop" id="editModal" hidden>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="editTitle">
      <div class="modal-header">
        <div>
          <div class="modal-title" id="editTitle">Topic bearbeiten</div>
          <div class="modal-sub" id="editSub"></div>
        </div>
        <button class="btn-ghost" type="button" onclick="closeEdit()">✕</button>
      </div>

      <div class="modal-section">
        <label for="editTopicId">Topic-ID</label>
        <input type="text" id="editTopicId" inputmode="numeric">
        <div class="form-hint">Die neue ID gilt für alle Aliase dieser Gruppe.</div>
      </div>

      <div class="modal-section">
        <label>Aliase</label>
        <div class="alias-list" id="editAliasList"></div>
        <div class="inline-form">
          <input type="text" id="aliasName" maxlength="128" placeholder="Neuer Alias…" autocomplete="off">
          <button class="btn-ghost" type="button" onclick="addAlias()">Hinzufügen</button>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-ghost" type="button" onclick="closeEdit()">Abbrechen</button>
        <button class="btn-primary" type="button" id="saveEditBtn" onclick="saveEdit()">Speichern</button>
      </div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

  <script>
    let currentChat = '';
    let topicsData = { topics: [], chats: [] };
    let editingTopic = null;
    let toastTimer = null;

    function escapeHtml(str) {
      if (str === null || str === undefined) return '';
      return String(str).replace(/[&<>"']/g, function(m) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[m];
      });
    }

    function showToast(message, type) {
      const el = document.getElementById('toast');
      el.innerText = message;
      el.className = 'toast show' + (type === 'error' ? ' error' : '');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function() { el.className = 'toast'; }, 4500);
    }

    async function apiFetch(url, options) {
      const res = await fetch(url, options);
      if (res.status === 401) {
        window.location.href = '/voduploader';
        throw new Error('Nicht angemeldet.');
      }
      const data = await res.json().catch(function() { return {}; });
      if (!res.ok) {
        throw new Error(data.error || ('HTTP ' + res.status));
      }
      return data;
    }

    function currentTopics() {
      const query = document.getElementById('searchInput').value.trim().toLowerCase();
      if (!query) return topicsData.topics;
      return topicsData.topics.filter(function(topic) {
        if (String(topic.topic_id).indexOf(query) !== -1) return true;
        if (topic.name.toLowerCase().indexOf(query) !== -1) return true;
        return topic.aliases.some(function(alias) {
          return alias.toLowerCase().indexOf(query) !== -1;
        });
      });
    }

    function renderTopics() {
      const topics = currentTopics();
      const body = document.getElementById('topicsBody');
      const emptyState = document.getElementById('emptyState');
      const tableWrap = document.getElementById('tableWrap');
      const totalAliases = topicsData.topics.reduce(function(sum, topic) {
        return sum + topic.aliases.length;
      }, 0);

      document.getElementById('summary').innerText =
        topicsData.topics.length + ' Topics · ' + totalAliases + ' Aliase' +
        (topics.length !== topicsData.topics.length ? ' · ' + topics.length + ' Treffer' : '');

      if (!topics.length) {
        body.innerHTML = '';
        tableWrap.hidden = true;
        emptyState.hidden = false;
        document.getElementById('emptyHint').innerText = topicsData.topics.length
          ? 'Kein Topic passt zur Suche.'
          : 'Füge oben ein Topic hinzu.';
        return;
      }

      tableWrap.hidden = false;
      emptyState.hidden = true;

      body.innerHTML = topics.map(function(topic) {
        const shown = topic.aliases.slice(0, 4).map(function(alias) {
          return '<span class="chip">' + escapeHtml(alias) + '</span>';
        }).join('');
        const rest = topic.aliases.length > 4
          ? '<span class="chip chip-more">+' + (topic.aliases.length - 4) + '</span>'
          : '';

        return '<tr>' +
          '<td><div class="topic-name">' + escapeHtml(topic.name) + '</div></td>' +
          '<td><span class="topic-id">#' + topic.topic_id + '</span></td>' +
          '<td><div class="chips">' + shown + rest + '</div></td>' +
          '<td>' +
            '<div class="row-actions">' +
              '<a class="btn-small" href="' + escapeHtml(topic.link) + '" target="_blank" rel="noopener">Öffnen</a>' +
              '<button class="btn-small" type="button" onclick="openEdit(' + topic.topic_id + ')">Bearbeiten</button>' +
              '<button class="btn-small danger" type="button" onclick="deleteTopic(' + topic.topic_id + ')">Löschen</button>' +
            '</div>' +
          '</td>' +
        '</tr>';
      }).join('');
    }

    function renderChats() {
      const wrap = document.getElementById('chatSelectWrap');
      const select = document.getElementById('chatSelect');
      const chats = topicsData.chats || [];
      if (chats.length <= 1) {
        wrap.hidden = true;
        return;
      }
      wrap.hidden = false;
      select.innerHTML = chats.map(function(chat) {
        return '<option value="' + escapeHtml(chat) + '"' +
          (String(chat) === String(topicsData.chat_id) ? ' selected' : '') + '>' +
          escapeHtml(chat) + (String(chat) === String(topicsData.forum_chat_id) ? ' (Forum)' : '') +
          '</option>';
      }).join('');
    }

    async function loadTopics() {
      try {
        const url = '/voduploader/api/topics' + (currentChat ? '?chat_id=' + encodeURIComponent(currentChat) : '');
        const data = await apiFetch(url);
        topicsData = data;
        currentChat = data.chat_id;
        document.getElementById('chatInfo').innerText = 'Chat: ' + data.chat_id;
        renderChats();
        renderTopics();
      } catch (err) {
        showToast('Topics konnten nicht geladen werden: ' + err.message, 'error');
        document.getElementById('summary').innerText = 'Fehler beim Laden.';
      }
    }

    function onChatChange() {
      currentChat = document.getElementById('chatSelect').value;
      loadTopics();
    }

    document.getElementById('newCreate').addEventListener('change', function() {
      document.getElementById('newTopicId').disabled = this.checked;
    });

    document.getElementById('addForm').addEventListener('submit', async function(event) {
      event.preventDefault();
      const name = document.getElementById('newName').value.trim();
      const create = document.getElementById('newCreate').checked;
      const topicIdRaw = document.getElementById('newTopicId').value.trim();

      if (!name) {
        showToast('Bitte einen Namen eingeben.', 'error');
        return;
      }
      if (!create && !topicIdRaw) {
        showToast('Bitte eine Topic-ID angeben oder „Im Telegram-Forum erstellen“ aktivieren.', 'error');
        return;
      }

      const btn = document.getElementById('addBtn');
      btn.disabled = true;
      btn.innerText = 'Speichere…';
      try {
        const body = { chat_id: currentChat, name: name, create: create };
        if (!create) body.topic_id = topicIdRaw;
        await apiFetch('/voduploader/api/topics', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        showToast("Topic '" + name + "' hinzugefügt.");
        document.getElementById('newName').value = '';
        document.getElementById('newTopicId').value = '';
        document.getElementById('newCreate').checked = false;
        document.getElementById('newTopicId').disabled = false;
        await loadTopics();
      } catch (err) {
        showToast(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = 'Hinzufügen';
      }
    });

    function openEdit(topicId) {
      const topic = topicsData.topics.find(function(item) {
        return item.topic_id === topicId;
      });
      if (!topic) return;
      editingTopic = topic;
      document.getElementById('editTitle').innerText = topic.name;
      document.getElementById('editSub').innerText =
        topic.aliases.length + ' Alias(e) · Topic #' + topic.topic_id;
      document.getElementById('editTopicId').value = topic.topic_id;
      document.getElementById('aliasName').value = '';
      renderEditAliases();
      document.getElementById('editModal').hidden = false;
    }

    function renderEditAliases() {
      if (!editingTopic) return;
      const list = document.getElementById('editAliasList');
      list.innerHTML = editingTopic.aliases.map(function(alias) {
        return '<span class="alias-row">' + escapeHtml(alias) +
          '<button type="button" class="alias-remove" title="Alias entfernen" data-alias="' +
          escapeHtml(alias) + '">×</button></span>';
      }).join('');
      list.querySelectorAll('.alias-remove').forEach(function(button) {
        button.addEventListener('click', function() {
          removeAlias(button.getAttribute('data-alias'));
        });
      });
    }

    function closeEdit() {
      document.getElementById('editModal').hidden = true;
      editingTopic = null;
    }

    async function saveEdit() {
      if (!editingTopic) return;
      const newTopicId = document.getElementById('editTopicId').value.trim();
      if (!/^[0-9]+$/.test(newTopicId) || parseInt(newTopicId, 10) <= 0) {
        showToast('Topic-ID muss eine positive Ganzzahl sein.', 'error');
        return;
      }
      const btn = document.getElementById('saveEditBtn');
      btn.disabled = true;
      btn.innerText = 'Speichere…';
      try {
        await apiFetch('/voduploader/api/topics', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: currentChat,
            topic_id: editingTopic.topic_id,
            new_topic_id: newTopicId
          })
        });
        showToast('Topic-ID aktualisiert.');
        closeEdit();
        await loadTopics();
      } catch (err) {
        showToast(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = 'Speichern';
      }
    }

    async function addAlias() {
      if (!editingTopic) return;
      const input = document.getElementById('aliasName');
      const name = input.value.trim();
      if (!name) {
        showToast('Bitte einen Alias eingeben.', 'error');
        return;
      }
      try {
        await apiFetch('/voduploader/api/topics/alias', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: currentChat,
            name: name,
            topic_id: editingTopic.topic_id
          })
        });
        showToast("Alias '" + name + "' hinzugefügt.");
        input.value = '';
        await reloadEditedTopic();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }

    async function removeAlias(alias) {
      if (!editingTopic) return;
      if (!confirm("Alias '" + alias + "' entfernen?")) return;
      try {
        await apiFetch('/voduploader/api/topics/alias?chat_id=' +
          encodeURIComponent(currentChat) + '&name=' + encodeURIComponent(alias), {
          method: 'DELETE'
        });
        showToast("Alias '" + alias + "' entfernt.");
        await reloadEditedTopic();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }

    async function reloadEditedTopic() {
      const id = editingTopic ? editingTopic.topic_id : null;
      const fallbackName = editingTopic ? editingTopic.name : '';
      await loadTopics();
      if (id === null) return;
      let updated = topicsData.topics.find(function(item) {
        return item.topic_id === id;
      });
      if (!updated) {
        updated = topicsData.topics.find(function(item) {
          return item.aliases.indexOf(fallbackName) !== -1;
        });
      }
      if (updated) openEdit(updated.topic_id);
      else closeEdit();
    }

    async function deleteTopic(topicId) {
      const topic = topicsData.topics.find(function(item) {
        return item.topic_id === topicId;
      });
      if (!topic) return;
      const message = "Topic '" + topic.name + "' (#" + topicId + ") mit " +
        topic.aliases.length + " Alias(en) löschen?\\n\\n" +
        'Beim nächsten Upload wird gegebenenfalls ein neues Telegram-Topic erstellt.';
      if (!confirm(message)) return;
      try {
        await apiFetch('/voduploader/api/topics?chat_id=' +
          encodeURIComponent(currentChat) + '&topic_id=' + encodeURIComponent(topicId), {
          method: 'DELETE'
        });
        showToast("Topic '" + topic.name + "' gelöscht.");
        closeEdit();
        await loadTopics();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }

    async function logout() {
      try {
        await fetch('/voduploader/api/logout', { method: 'POST' });
      } catch (e) {}
      window.location.href = '/voduploader';
    }

    document.addEventListener('keydown', function(event) {
      if (event.key === 'Escape' && !document.getElementById('editModal').hidden) {
        closeEdit();
      }
    });

    loadTopics();
  </script>
</body>
</html>
"""
