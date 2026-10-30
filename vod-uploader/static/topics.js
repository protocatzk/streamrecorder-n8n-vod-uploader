let currentChat = '';
let topicsData = { topics: [], chats: [] };
let editingTopic = null;
let toastTimer = null;

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
    topic.aliases.length + " Alias(en) löschen?\n\n" +
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

document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape' && !document.getElementById('editModal').hidden) {
    closeEdit();
  }
});

loadTopics();
