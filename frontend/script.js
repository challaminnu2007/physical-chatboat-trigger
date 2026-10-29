/**
 * Physical Chatbot Trigger — Frontend Script
 * ─────────────────────────────────────────────
 * SECURITY NOTE:
 *   The API endpoint URL is the ONLY value that belongs here.
 *   Discord webhook URL, AWS credentials, and secrets must NEVER
 *   appear in this file. All sensitive operations happen in Lambda.
 *
 * LOCAL DEV:  python backend/local_server.py   → http://localhost:5000
 * PRODUCTION: replace AWS_API_ENDPOINT below with your API Gateway URL.
 */

'use strict';

/* ════════════════════════════════════════════════
   CONFIGURATION
   ─ If backend is hosted separately (e.g. on Render or AWS API Gateway):
     Set BACKEND_API_URL below (e.g. 'https://my-backend.onrender.com').
   ─ If running locally or fullstack on Render (all-in-one):
     Leave BACKEND_API_URL empty (''), and it auto-uses the current domain!
════════════════════════════════════════════════ */
const BACKEND_API_URL = '';
// Examples:
// Render: 'https://physical-chatbot-backend.onrender.com'
// AWS:    'https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod'

/**
 * Auto-resolves the API endpoint:
 *   • Explicit BACKEND_API_URL if configured
 *   • On Vercel: prompts to configure backend URL if not set
 *   • Localhost or all-in-one Render: uses current origin /alert
 */
function getApiEndpoint() {
  if (BACKEND_API_URL && !BACKEND_API_URL.includes('YOUR_API_GATEWAY')) {
    const trimmed = BACKEND_API_URL.replace(/\/+$/, '');
    return trimmed.endsWith('/alert') ? trimmed : `${trimmed}/alert`;
  }
  // Default to same origin /alert (works locally, all-in-one Render, and Vercel serverless)
  return `${window.location.origin}/alert`;
}

const API_ENDPOINT = getApiEndpoint();

/* ════════════════════════════════════════════════
   CONSTANTS
════════════════════════════════════════════════ */
const MAX_CHARS       = 500;
const MAX_HISTORY_UI  = 20;   // items to show at once in history panel
const TOAST_DURATION  = 5000; // ms

/* ════════════════════════════════════════════════
   STATE
════════════════════════════════════════════════ */
const state = {
  total:   0,
  success: 0,
  failed:  0,
  history: [],       // [{id, message, sender, status, timestamp}]
  sending: false,
};

/* ════════════════════════════════════════════════
   DOM REFERENCES
════════════════════════════════════════════════ */
const $ = id => document.getElementById(id);

const DOM = {
  form:        $('alertForm'),
  messageInput:$('messageInput'),
  senderName:  $('senderName'),
  sendBtn:     $('sendBtn'),
  spinner:     $('spinner'),
  btnText:     document.querySelector('#sendBtn .btn-text'),
  btnIcon:     document.querySelector('#sendBtn .btn-icon'),
  charCount:   $('charCount'),
  msgError:    $('msgError'),
  toast:       $('toast'),
  historyList: $('historyList'),
  historyEmpty:$('historyEmpty'),
  loadMoreBtn: $('loadMoreBtn'),
  refreshBtn:  $('refreshBtn'),
  statTotal:   $('statTotal'),
  statSuccess: $('statSuccess'),
  statFailed:  $('statFailed'),
  statusDot:   $('statusDot'),
  statusLabel: $('statusLabel'),
  presets:     document.querySelectorAll('.preset-btn'),
};

/* ════════════════════════════════════════════════
   INITIALISATION
════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  setupCharCounter();
  setupPresetButtons();
  setupForm();
  setupRefreshButton();
  checkApiStatus();
});

/* ════════════════════════════════════════════════
   CHARACTER COUNTER
════════════════════════════════════════════════ */
function setupCharCounter() {
  DOM.messageInput.addEventListener('input', () => {
    const len = DOM.messageInput.value.length;
    DOM.charCount.textContent = `${len} / ${MAX_CHARS}`;
    DOM.charCount.className = 'char-count';
    if (len > MAX_CHARS * 0.85) DOM.charCount.classList.add('warning');
    if (len >= MAX_CHARS)        DOM.charCount.classList.add('danger');
    if (len > 0) clearFieldError();
  });
}

/* ════════════════════════════════════════════════
   PRESET BUTTONS
════════════════════════════════════════════════ */
function setupPresetButtons() {
  DOM.presets.forEach(btn => {
    btn.addEventListener('click', () => {
      const msg = btn.dataset.msg || btn.textContent.trim();
      DOM.messageInput.value = msg;
      DOM.charCount.textContent = `${msg.length} / ${MAX_CHARS}`;
      DOM.messageInput.focus();
      clearFieldError();
      // Animate the textarea briefly to indicate the fill
      DOM.messageInput.classList.add('is-preset-fill');
      setTimeout(() => DOM.messageInput.classList.remove('is-preset-fill'), 600);
    });
  });
}

/* ════════════════════════════════════════════════
   FORM SUBMISSION
════════════════════════════════════════════════ */
function setupForm() {
  DOM.form.addEventListener('submit', async e => {
    e.preventDefault();
    if (state.sending) return;

    const message = DOM.messageInput.value.trim();
    const sender  = DOM.senderName.value.trim() || 'Dashboard User';

    // Validation
    if (!message) {
      showFieldError('Please enter a message before sending.');
      DOM.messageInput.focus();
      return;
    }
    if (message.length > MAX_CHARS) {
      showFieldError(`Message too long. Max ${MAX_CHARS} characters.`);
      return;
    }

    // Check endpoint is configured
    if (!API_ENDPOINT) {
      showToast('error', '⚙️ Backend not configured. Set BACKEND_API_URL in frontend/script.js to your Render or AWS endpoint.');
      return;
    }

    await sendAlert(message, sender);
  });
}

/* ════════════════════════════════════════════════
   SEND ALERT — core function
════════════════════════════════════════════════ */
async function sendAlert(message, sender) {
  setLoadingState(true);
  hideToast();

  const payload = {
    message,
    sender,
    timestamp: new Date().toISOString(),
    source:    'web-dashboard',
  };

  let result = null;

  try {
    const response = await fetch(API_ENDPOINT, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));

    if (response.ok) {
      result = {
        id:        data.alertId || generateLocalId(),
        message,
        sender,
        status:    'success',
        timestamp: new Date().toISOString(),
      };
      incrementStats('success');
      showToast('success', `✅ Alert sent to Discord! ID: ${result.id.slice(-8)}`);
      resetForm();
    } else {
      const errMsg = data.error || data.message || `HTTP ${response.status}`;
      result = {
        id:        generateLocalId(),
        message,
        sender,
        status:    'error',
        timestamp: new Date().toISOString(),
        error:     errMsg,
      };
      incrementStats('failed');
      showToast('error', `❌ Failed: ${errMsg}`);
    }
  } catch (err) {
    result = {
      id:        generateLocalId(),
      message,
      sender,
      status:    'error',
      timestamp: new Date().toISOString(),
      error:     err.message || 'Network error',
    };
    incrementStats('failed');

    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      showToast('error', '🔌 Cannot reach API. Check your network and API_ENDPOINT value.');
    } else {
      showToast('error', `❌ Error: ${err.message}`);
    }
  } finally {
    setLoadingState(false);
    if (result) addHistoryItem(result);
  }
}

/* ════════════════════════════════════════════════
   HISTORY MANAGEMENT
════════════════════════════════════════════════ */
function addHistoryItem(item) {
  state.history.unshift(item);
  if (state.history.length > 100) state.history.pop();
  renderHistory();
}

function renderHistory() {
  // Hide empty state
  const hasItems = state.history.length > 0;
  DOM.historyEmpty.style.display = hasItems ? 'none' : '';

  // Remove old rendered items (not the empty placeholder)
  DOM.historyList.querySelectorAll('.history-item').forEach(el => el.remove());

  const visible = state.history.slice(0, MAX_HISTORY_UI);
  visible.forEach(item => {
    DOM.historyList.appendChild(createHistoryElement(item));
  });

  // Load more button
  DOM.loadMoreBtn.hidden = state.history.length <= MAX_HISTORY_UI;
}

function createHistoryElement(item) {
  const el = document.createElement('div');
  el.className = 'history-item';
  el.setAttribute('role', 'listitem');

  const statusClass = item.status === 'success' ? 'success' : 'error';
  const badgeLabel  = item.status === 'success' ? '✓' : '✗';
  const timeStr     = formatTimestamp(item.timestamp);

  el.innerHTML = `
    <div class="history-badge badge--${statusClass}" aria-label="${item.status}">
      ${badgeLabel}
    </div>
    <div class="history-content">
      <span class="history-msg" title="${escapeHtml(item.message)}">${escapeHtml(item.message)}</span>
      <div class="history-meta">
        <span>${escapeHtml(item.sender || 'Unknown')}</span>
        <span>·</span>
        <span>${timeStr}</span>
        <span>·</span>
        <span class="history-status ${statusClass}">${item.status.toUpperCase()}</span>
        ${item.error ? `<span title="${escapeHtml(item.error)}">⚠️</span>` : ''}
      </div>
    </div>
  `;
  return el;
}

/* ════════════════════════════════════════════════
   API STATUS CHECK
════════════════════════════════════════════════ */
async function checkApiStatus() {
  if (!API_ENDPOINT) {
    setStatus('offline', 'Backend URL needed');
    return;
  }

  try {
    // Use a HEAD or OPTIONS request to check if the endpoint is reachable
    // We expect CORS or 2xx; a 4xx from a mis-configured route is still "online"
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 5000);
    const res = await fetch(API_ENDPOINT, {
      method: 'OPTIONS',
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    // Any HTTP response means the server is reachable
    setStatus('online', 'API Online');
  } catch {
    setStatus('offline', 'API Offline');
  }
}

async function refreshHistory() {
  // When the backend supports a GET /alerts endpoint, fetch real history here.
  // For now, re-render what we have in memory and do a status recheck.
  DOM.refreshBtn.style.transform = 'rotate(360deg)';
  await checkApiStatus();
  setTimeout(() => { DOM.refreshBtn.style.transform = ''; }, 500);
}

function setupRefreshButton() {
  DOM.refreshBtn.addEventListener('click', refreshHistory);
}

/* ════════════════════════════════════════════════
   UI HELPERS
════════════════════════════════════════════════ */
function setLoadingState(loading) {
  state.sending = loading;
  DOM.sendBtn.disabled    = loading;
  DOM.spinner.hidden      = !loading;
  DOM.btnIcon.hidden      =  loading;
  DOM.btnText.textContent = loading ? 'Sending…' : 'Send Alert';
  DOM.presets.forEach(b => { b.disabled = loading; });
}

function resetForm() {
  DOM.messageInput.value = '';
  DOM.charCount.textContent = `0 / ${MAX_CHARS}`;
  DOM.charCount.className = 'char-count';
  clearFieldError();
}

function showFieldError(msg) {
  DOM.msgError.textContent = msg;
  DOM.messageInput.classList.add('is-error');
}
function clearFieldError() {
  DOM.msgError.textContent = '';
  DOM.messageInput.classList.remove('is-error');
}

let toastTimer = null;
function showToast(type, msg) {
  DOM.toast.className = `toast ${type}`;
  DOM.toast.textContent = msg;
  DOM.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, TOAST_DURATION);
}
function hideToast() {
  DOM.toast.hidden = true;
}

function setStatus(state, label) {
  DOM.statusDot.className = `status-dot ${state}`;
  DOM.statusLabel.textContent = label;
}

function incrementStats(type) {
  state.total++;
  if (type === 'success') state.success++;
  else                    state.failed++;

  animateStat(DOM.statTotal,   state.total);
  animateStat(DOM.statSuccess, state.success);
  animateStat(DOM.statFailed,  state.failed);
}

function animateStat(el, value) {
  el.textContent = value;
  el.classList.remove('bump');
  // Force reflow to restart animation
  void el.offsetWidth;
  el.classList.add('bump');
}

/* ════════════════════════════════════════════════
   UTILITIES
════════════════════════════════════════════════ */
function generateLocalId() {
  return 'local-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

function formatTimestamp(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso;
  }
}

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
