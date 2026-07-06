'use strict';

document.addEventListener('DOMContentLoaded', () => {
  loadAll();
  startCountdown();
});

async function loadAll() {
  try {
    const [rankData, histData] = await Promise.all([
      fetch('rankings.json').then(r => r.json()),
      fetch('history.json').then(r => r.json()),
    ]);
    renderRankings(rankData);
    renderChart(histData);
    setLastUpdated(rankData.last_updated);
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
  const keys = ['mmlu', 'humaneval', 'math'];
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

  // Sort percentage benchmarks high → low, color the top scorer per category
  const b = tool.benchmarks || {};
  const pctBenchmarks = [
    { label: 'Reasoning', val: b.mmlu,      key: 'mmlu' },
    { label: 'Coding',    val: b.humaneval, key: 'humaneval' },
    { label: 'Math',      val: b.math,      key: 'math' },
  ].filter(x => x.val != null).sort((a, z) => z.val - a.val);

  const bChips = pctBenchmarks.map(x => {
    const isTop = x.val === topScores[x.key];
    const isTie = isTop && topCounts[x.key] > 1;
    const style = isTop
      ? isTie
        ? 'border-color:rgba(32,201,151,0.3);background:rgba(32,201,151,0.08);color:#6ee8c8;'
        : 'border-color:rgba(32,201,151,0.6);background:rgba(32,201,151,0.18);color:#20c997;'
      : '';
    return `<span class="bench-chip"${style ? ` style="${style}"` : ''}>${x.label}&nbsp;${x.val.toFixed(0)}%</span>`;
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

// ── Chart ─────────────────────────────────────────────────────────────────────

function renderChart(data) {
  const series = data.series || [];
  const ctx = document.getElementById('lineChart').getContext('2d');

  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.months,
      datasets: series.map(s => ({
        label: s.name,
        data: s.score,
        borderColor: s.color,
        backgroundColor: 'transparent',
        borderWidth: s.in_cards ? 2.5 : 1.5,
        pointBackgroundColor: s.color,
        pointRadius: 3,
        pointHoverRadius: 3,
        tension: 0.3,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#888ab0', font: { size: 11, family: 'Inter' } },
          border: { color: 'rgba(255,255,255,0.08)' },
        },
        y: {
          min: 45,
          max: 95,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: {
            color: '#888ab0',
            font: { size: 11, family: 'Inter' },
            callback: v => v,
          },
          border: { color: 'rgba(255,255,255,0.08)' },
          title: {
            display: true,
            text: 'Composite Score (0–100)',
            color: '#888ab0',
            font: { size: 10, family: 'Inter' },
          },
        },
      },
    },
  });

  // Interactive legend: click to highlight one line, dim the rest
  const legendEl = document.getElementById('chartLegend');
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
        ds.borderWidth = on ? (series[i].in_cards ? 2.5 : 1.5) : 1;
      });
      chart.update('none');

      legendEl.querySelectorAll('.legend-item').forEach((li, i) => {
        li.style.opacity = (activeIdx === null || i === activeIdx) ? '1' : '0.3';
      });
    });

    legendEl.appendChild(item);
  });
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
    if (diff <= 0) { el.textContent = 'now'; return; }
    const d = Math.floor(diff / 86_400_000);
    const h = Math.floor((diff % 86_400_000) / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    el.textContent = d > 0 ? `${d}d ${pad(h)}h ${pad(m)}m` : `${pad(h)}h ${pad(m)}m`;
  };
  tick();
  setInterval(tick, 60_000);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setLastUpdated(iso) {
  const el = document.getElementById('last-updated');
  try {
    const d = new Date(iso);
    el.textContent = `Updated: ${d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`;
  } catch { el.textContent = `Updated: ${iso}`; }
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
