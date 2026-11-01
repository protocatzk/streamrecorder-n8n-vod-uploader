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

      <div class="job-actions">
        ${job.stage === 'cancelling'
          ? '<button class="btn-cancel" disabled>Abbruch läuft…</button>'
          : `<button class="btn-cancel" onclick="cancelJob('${escapeHtml(job.key || '')}', this)">Job abbrechen</button>`}
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
      <div class="queue-right">
        <div class="queue-pos">#${idx + 1}</div>
        <button class="btn-cancel btn-cancel-sm" title="Job abbrechen" onclick="cancelJob('${escapeHtml(item.key || '')}', this)">✕</button>
      </div>
    </div>
  `).join('');
}

async function cancelJob(key, btn) {
  if (!key) return;
  if (!confirm('Job wirklich abbrechen?\nBereits nach Telegram hochgeladene Teile werden wieder gelöscht.')) {
    return;
  }
  const original = btn ? btn.innerText : '';
  if (btn) {
    btn.disabled = true;
    btn.innerText = '...';
  }
  try {
    const res = await fetch('/voduploader/api/jobs/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: key })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch (e) {
    if (btn) {
      btn.disabled = false;
      btn.innerText = original;
    }
    alert('Abbruch fehlgeschlagen. Bitte Log prüfen.');
  }
}

function renderHistory(history) {
  const tbody = document.getElementById('historyTableBody');
  const count = document.getElementById('historyCount');
  count.innerText = `${history.length} Einträge`;

  if (!history || history.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">Noch keine VODs in dieser Session hochgeladen.</td></tr>';
    return;
  }

  tbody.innerHTML = history.map(item => {
    const isSuccess = item.status === 'success';
    const isCancelled = item.status === 'cancelled';
    const statusBadge = isSuccess 
      ? '<span style="color: var(--emerald); font-weight: 600;">✓ Fertig</span>'
      : isCancelled
        ? '<span style="color: #f59e0b; font-weight: 600;">⊘ Abgebrochen</span>'
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
  } else if (rss.cookies && rss.cookies.broken) {
    badge.className = 'badge badge-live';
    badge.innerText = 'COOKIES UNGÜLTIG';
    badge.title = rss.cookies.reason || 'Cookie-Datei ersetzen und Retries zurücksetzen';
  } else if (rss.blocked_until && rss.blocked_until > Date.now() / 1000) {
    badge.className = 'badge badge-live';
    badge.innerText = 'YOUTUBE BLOCKIERT';
    badge.title = 'Bot-Check aktiv – Cookies/PO-Provider prüfen';
  } else if (rss.running) {
    badge.className = 'badge badge-live';
    badge.innerText = rss.processing ? 'VERARBEITET' : 'LÄUFT';
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

async function resetRssRetries() {
  const btn = document.getElementById('rssRetryBtn');
  btn.disabled = true;
  btn.innerText = 'Setze zurück...';
  let label = 'Retries zurücksetzen';
  try {
    const res = await fetch('/voduploader/api/rss/retry', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (res.ok) label = `${data.reset || 0} zurückgesetzt`;
    else if (res.status === 401) label = 'Login abgelaufen';
    else label = 'Fehler';
  } catch (e) {
    label = 'Fehler';
  }
  btn.innerText = label;
  setTimeout(() => {
    btn.disabled = false;
    btn.innerText = 'Retries zurücksetzen';
  }, 5000);
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

initialFetch();
connectSSE();
