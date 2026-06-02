'use strict';

// ── State ────────────────────────────────────────────────
let nextRefreshAt = null;
let countdownTimer = null;

// ── Bootstrap ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadAll();
  scheduleMidnightReload();
});

async function loadAll() {
  await Promise.all([loadRankings(), loadNews()]);
}

// ── Rankings ─────────────────────────────────────────────
async function loadRankings() {
  try {
    const res = await fetch('/api/rankings');
    const data = await res.json();
    renderRankings(data);
    setLastUpdated(data.last_updated);
  } catch (err) {
    console.error('Rankings fetch failed:', err);
  }
}

function renderRankings(data) {
  const grid = document.getElementById('rankings-grid');
  grid.innerHTML = '';

  data.tools.forEach((tool, idx) => {
    const card = buildRankCard(tool);
    card.style.animationDelay = `${idx * 60}ms`;
    card.style.animation = 'fadeUp 0.45s ease both';
    grid.appendChild(card);
  });

  // Animate score bars after paint
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.querySelectorAll('.score-bar-fill').forEach(bar => {
        bar.style.width = bar.dataset.target + '%';
      });
    });
  });
}

function buildRankCard(tool) {
  const card = document.createElement('div');
  card.className = `rank-card rank-${tool.rank}`;
  card.style.setProperty('--tool-color', tool.color || '#667eea');

  const rankClass = tool.rank === 1 ? 'gold' : tool.rank === 2 ? 'silver' : tool.rank === 3 ? 'bronze' : 'plain';
  const rankEmoji = tool.rank === 1 ? '🥇' : tool.rank === 2 ? '🥈' : tool.rank === 3 ? '🥉' : `#${tool.rank}`;

  const maxScore = 100;
  const barPct = Math.min((tool.score / maxScore) * 100, 100).toFixed(1);

  const m = tool.metrics;

  card.innerHTML = `
    <div class="card-top">
      <div class="card-identity">
        <div class="tool-icon">${tool.icon}</div>
        <div>
          <div class="tool-name">${esc(tool.name)}</div>
          <div class="tool-company">${esc(tool.company)}</div>
        </div>
      </div>
      <div class="rank-badge ${rankClass}">${rankEmoji}</div>
    </div>

    <p class="tool-desc">${esc(tool.description)}</p>

    <div class="score-section">
      <div class="score-row">
        <span class="score-label">Overall Score</span>
        <span class="score-value">${tool.score}</span>
      </div>
      <div class="score-bar-track">
        <div class="score-bar-fill" data-target="${barPct}"></div>
      </div>
    </div>

    <div class="metrics-row">
      <span class="metric-chip">👥 <span class="val">${m.monthly_users}M</span> users/mo</span>
      <span class="metric-chip">📈 <span class="val">+${m.growth_rate}%</span> growth</span>
      <span class="metric-chip">🧠 <span class="val">${m.capability_score}</span> capability</span>
      <span class="metric-chip">🌐 <span class="val">${m.community_score}</span> community</span>
    </div>

    <a class="card-link" href="${esc(tool.url)}" target="_blank" rel="noopener">
      Visit ${esc(tool.name)} ↗
    </a>
  `;

  return card;
}

// ── News ─────────────────────────────────────────────────
async function loadNews() {
  try {
    const res = await fetch('/api/news');
    const data = await res.json();
    renderNews(data.articles || [], data.source === 'seed');
  } catch (err) {
    console.error('News fetch failed:', err);
    document.getElementById('news-grid').innerHTML = '';
    document.getElementById('news-empty').classList.remove('hidden');
  }
}

function renderNews(articles, isSeed = false) {
  const grid = document.getElementById('news-grid');
  const empty = document.getElementById('news-empty');

  grid.innerHTML = '';

  if (!articles.length) {
    empty.classList.remove('hidden');
    return;
  }

  empty.classList.add('hidden');

  if (isSeed) {
    const notice = document.createElement('p');
    notice.className = 'seed-notice';
    notice.textContent = '📡 Showing curated articles — live RSS updates when network is available';
    grid.before(notice);
  } else {
    document.querySelector('.seed-notice')?.remove();
  }

  articles.forEach((article, idx) => {
    const card = buildNewsCard(article);
    card.style.animationDelay = `${idx * 40}ms`;
    card.style.animation = 'fadeUp 0.4s ease both';
    grid.appendChild(card);
  });
}

function buildNewsCard(article) {
  const card = document.createElement('a');
  card.className = 'news-card';
  card.href = article.url;
  card.target = '_blank';
  card.rel = 'noopener noreferrer';

  const dateStr = formatDate(article.published);

  card.innerHTML = `
    <span class="news-source-badge">${esc(article.source)}</span>
    <div class="news-title">${esc(article.title)}</div>
    ${article.summary ? `<div class="news-summary">${esc(article.summary)}</div>` : ''}
    ${dateStr ? `<div class="news-date">${dateStr}</div>` : ''}
  `;

  return card;
}

// ── Manual Refresh ────────────────────────────────────────
async function manualRefresh() {
  const btn = document.getElementById('btn-refresh');
  const icon = document.getElementById('refresh-icon');
  btn.disabled = true;
  icon.classList.add('spinning');

  try {
    await fetch('/api/refresh', { method: 'POST' });
    await loadAll();
    showToast('✅ Rankings and news refreshed!', 'success');
  } catch (err) {
    showToast('❌ Refresh failed. Please try again.', 'error');
  } finally {
    btn.disabled = false;
    icon.classList.remove('spinning');
  }
}

// ── Daily Auto-Refresh ────────────────────────────────────
function scheduleMidnightReload() {
  const now = new Date();
  const midnight = new Date();
  midnight.setUTCHours(24, 0, 0, 0);
  nextRefreshAt = midnight;

  const msUntilMidnight = midnight - now;

  startCountdown();

  setTimeout(async () => {
    await loadAll();
    showToast('🔄 Daily refresh complete!', 'success');
    scheduleMidnightReload(); // reschedule for next day
  }, msUntilMidnight);
}

function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);

  const el = document.getElementById('countdown');

  const tick = () => {
    if (!nextRefreshAt) return;
    const diff = nextRefreshAt - Date.now();
    if (diff <= 0) { el.textContent = 'now'; return; }
    const h = Math.floor(diff / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    const s = Math.floor((diff % 60_000) / 1_000);
    el.textContent = `${pad(h)}h ${pad(m)}m ${pad(s)}s`;
  };

  tick();
  countdownTimer = setInterval(tick, 1000);
}

// ── Helpers ───────────────────────────────────────────────
function setLastUpdated(iso) {
  const el = document.getElementById('last-updated');
  if (!iso) return;
  try {
    const d = new Date(iso);
    el.textContent = `Updated: ${d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`;
  } catch {
    el.textContent = `Updated: ${iso}`;
  }
}

function formatDate(str) {
  if (!str) return '';
  try {
    const d = new Date(str);
    if (isNaN(d)) return str;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return str;
  }
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function pad(n) { return String(n).padStart(2, '0'); }

function showToast(msg, type = '') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className = `toast show ${type}`;
  setTimeout(() => { toast.className = 'toast hidden'; }, 3500);
}

// CSS animation (injected once)
const style = document.createElement('style');
style.textContent = `
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`;
document.head.appendChild(style);
