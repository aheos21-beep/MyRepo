'use strict';

document.addEventListener('DOMContentLoaded', () => {
  loadAll();
  startCountdown();
});

async function loadAll() {
  try {
    // Cache-bust the data files so a cached copy never masks a fresh refresh.
    const v = Date.now();
    const [rankData, histData] = await Promise.all([
      fetch(`rankings.json?v=${v}`).then(r => r.json()),
      fetch(`history.json?v=${v}`).then(r => r.json()),
    ]);
    renderRankings(rankData);
    renderChart(histData);
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
  // A vendor missing from VENDOR_META has no product URL. Render it as a plain
  // div rather than an anchor with href="", which would "link" to this page.
  const hasUrl = Boolean(tool.url);
  const card = document.createElement(hasUrl ? 'a' : 'div');
  card.className = `rank-card rank-${tool.rank}${hasUrl ? '' : ' no-link'}`;
  if (hasUrl) {
    card.href = tool.url;
    card.target = '_blank';
    card.rel = 'noopener noreferrer';
  }
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
        <div class="score-badge" style="color:${tool.color}">${tool.score}</div>
        <div class="rank-badge ${rankClass}">${rankEmoji}</div>
      </div>
    </div>
    <div class="bench-row">${bChips}</div>
  `;
  return card;
}

// ── Chart ─────────────────────────────────────────────────────────────────────

function renderChart(data) {
  const series = data.series || [];
  const canvas = document.getElementById('lineChart');
  if (!canvas) return;

  // Never fail silently: a missing chart library used to leave a blank panel
  // with no clue why. Say so on the page instead.
  if (typeof Chart === 'undefined') {
    canvas.parentElement.innerHTML =
      '<div class="chart-error">Chart library failed to load.' +
      '<br><small>Ranking data loaded fine — try a hard refresh.</small></div>';
    return;
  }

  const chart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: data.months,
      datasets: series.map(s => ({
        label: s.name,
        data: s.score,
        borderColor: s.color,
        backgroundColor: 'transparent',
        borderWidth: 2.5,
        pointBackgroundColor: s.color,
        pointRadius: 3,
        pointHoverRadius: 3,
        tension: 0.3,
        // Null means the model was not on that snapshot's board. Leave the gap
        // visible rather than drawing a line across data we do not have.
        spanGaps: false,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#888ab0', font: { size: 11, family: 'Inter' } },
          border: { color: 'rgba(255,255,255,0.08)' },
        },
        y: {
          // Auto-scaled: Arena ELO is unbounded and the top models sit in a
          // narrow band, so a fixed window would either clip or flatten it.
          grace: '8%',
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#888ab0', font: { size: 11, family: 'Inter' } },
          border: { color: 'rgba(255,255,255,0.08)' },
          title: {
            display: true,
            text: 'Arena ELO ÷ 10',
            color: '#888ab0',
            font: { size: 10, family: 'Inter' },
          },
        },
      },
    },
  });

  // Interactive legend: click to highlight one line, dim the rest
  const legendEl = document.getElementById('chartLegend');
  if (!legendEl) return;
  let activeIdx = null;

  series.forEach((s, idx) => {
    const item = document.createElement('div');
    item.className = 'legend-item';
    item.innerHTML = `<div class="legend-dot" style="background:${s.color}"></div>${esc(s.name)}`;

    item.addEventListener('click', () => {
      activeIdx = (activeIdx === idx) ? null : idx;
      chart.data.datasets.forEach((ds, i) => {
        const base = series[i].color;
        const on = activeIdx === null || i === activeIdx;
        ds.borderColor = on ? base : base + '28';
        ds.pointBackgroundColor = on ? base : base + '28';
        ds.borderWidth = on ? 2.5 : 1;
      });
      chart.update('none');
      legendEl.querySelectorAll('.legend-item').forEach((li, i) => {
        li.style.opacity = (activeIdx === null || i === activeIdx) ? '1' : '0.3';
      });
    });

    legendEl.appendChild(item);
  });
}

// ── Countdown (next daily run at 9am UTC) ─────────────────────────────────────

function nextRefreshTime() {
  const now = new Date();
  const t = new Date(Date.UTC(
    now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 9, 0, 0
  ));
  if (t <= now) t.setUTCDate(t.getUTCDate() + 1);
  return t;
}

function startCountdown() {
  const el = document.getElementById('countdown');
  const tick = () => {
    // Always under 24h now, so report hours/minutes rather than days.
    const diff = nextRefreshTime() - Date.now();
    if (diff <= 0) { el.textContent = 'now'; return; }
    const h = Math.floor(diff / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    el.textContent = h >= 1 ? `${h}h ${m}m` : `${m}m`;
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
