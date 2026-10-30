/* Gemeinsame Helfer für Dashboard und Topic-Verwaltung. */

async function logout() {
  try {
    await fetch('/voduploader/api/logout', { method: 'POST' });
  } catch (e) {}
  window.location.href = '/voduploader';
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, function(m) {
    return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[m];
  });
}
