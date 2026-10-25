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
      <div class="stat-card">
        <div class="stat-label">Topics gemappt</div>
        <div class="stat-value" id="topicCount">-</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Ziel-Forum</div>
        <div class="stat-value" style="font-size: 1.15rem; color: #a5b4fc;">Ripper Archiv</div>
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
