'use strict';

document.addEventListener('DOMContentLoaded', () => {
  loadAll();
  startCountdown();
});

async function loadAll() {
  try {
    const rankData = await fetch('rankings.json').then(r => r.json());
    renderRankings(rankData);
    setLastUpdated(rankData.last_updated);
    setCost(rankData.api_cost);
  } catch (err) {
    console.error('Load failed:', err);
  }
}

// ── Rankings ──────────────────────────────────────────────────────────────────

function renderRankings(data) {
  const grid = document.getElementById('rankings-grid');
  grid.innerHTML = '';
  const tools = data.tools.slice(0, 5);

  // Find top score and count of ties for each benchmark category
  const keys = ['code', 'vision', 'document'];
  const topScores = {}, topCounts = {};
  keys.forEach(k => {
    topScores[k] = Math.max(...tools.map(t => (t.benchmarks || {})[k] ?? 0));
    topCounts[k] = tools.filter(t => ((t.benchmarks || {})[k] ?? 0) === topScores[k]).length;
  });

  tools.forEach((tool, idx) => {
    const card = buildRankCard(tool, topScores, topCounts);
    card.style.animationDelay = `${idx * 60}ms`;
    card.style.animation = 'fadeUp 0.45s ease both';
    grid.appendChild(card);
  });
}

function buildRankCard(tool, topScores = {}, topCounts = {}) {
  const card = document.createElement('a');
  card.className = `rank-card rank-${tool.rank}`;
  card.href = tool.url;
  card.target = '_blank';
  card.rel = 'noopener noreferrer';
  card.style.setProperty('--tool-color', tool.color || '#667eea');

  const rankClass = ['', 'gold', 'silver', 'bronze'][tool.rank] || 'plain';
  const rankEmoji = ['', '🥇', '🥈', '🥉'][tool.rank] || `#${tool.rank}`;

  // Sort category scores high → low, color the top scorer per category
  const b = tool.benchmarks || {};
  const pctBenchmarks = [
    { label: 'Code',     val: b.code,     key: 'code' },
    { label: 'Vision',   val: b.vision,   key: 'vision' },
    { label: 'Document', val: b.document, key: 'document' },
  ].filter(x => x.val != null).sort((a, z) => z.val - a.val);

  const bChips = pctBenchmarks.map(x => {
    const isTop = x.val === topScores[x.key];
    const isTie = isTop && topCounts[x.key] > 1;
    const style = isTop
      ? isTie
        ? 'border-color:rgba(32,201,151,0.3);background:rgba(32,201,151,0.08);color:#6ee8c8;'
        : 'border-color:rgba(32,201,151,0.6);background:rgba(32,201,151,0.18);color:#20c997;'
      : '';
    return `<span class="bench-chip"${style ? ` style="${style}"` : ''}>${x.label}&nbsp;${x.val.toFixed(0)}</span>`;
  }).join('');

  card.innerHTML = `
    <div class="card-top">
      <div class="card-identity">
        <div class="tool-icon">${tool.icon}</div>
        <div>
          <div class="tool-name">${esc(tool.name)} <span class="tool-version">(${esc(tool.model)})</span></div>
          <div class="tool-company">${esc(tool.company)}</div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
        <div class="score-badge" style="color:${tool.color}">${tool.score}<span class="score-denom">/100</span></div>
        <div class="rank-badge ${rankClass}">${rankEmoji}</div>
      </div>
    </div>
    <div class="bench-row">${bChips}</div>
  `;
  return card;
}

// ── Countdown (next 1st or 15th at 9am UTC) ───────────────────────────────────

function nextRefreshTime() {
  const now = new Date();
  const candidates = [];
  for (let offset = 0; offset <= 1; offset++) {
    const base = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + offset, 1));
    for (const day of [1, 15]) {
      const t = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), day, 9, 0, 0));
      if (t > now) candidates.push(t);
    }
  }
  return candidates.reduce((a, b) => a < b ? a : b);
}

function startCountdown() {
  const el = document.getElementById('countdown');
  const tick = () => {
    const diff = nextRefreshTime() - Date.now();
    if (diff <= 0) { el.textContent = 'today'; return; }
    const d = Math.floor(diff / 86_400_000);
    el.textContent = d === 1 ? '1 day' : `${d} days`;
  };
  tick();
  setInterval(tick, 60_000);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function ordinalDay(n) {
  const s = ['th','st','nd','rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function setLastUpdated(iso) {
  const el = document.getElementById('last-updated');
  try {
    const d = new Date(iso);
    const mon = d.toLocaleDateString('en-US', { month: 'short' });
    el.textContent = `${mon} ${ordinalDay(d.getDate())}`;
  } catch { el.textContent = '—'; }
}

function setCost(cost) {
  const el = document.getElementById('api-cost');
  if (el) el.textContent = cost || '—';
}

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function pad(n) { return String(n).padStart(2, '0'); }

const style = document.createElement('style');
style.textContent = `
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`;
document.head.appendChild(style);
