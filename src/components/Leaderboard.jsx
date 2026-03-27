import React from 'react'
import { leaderboardData, benchmarks } from '../data/benchmarks.js'

const rankStyle = (rank) => {
  if (rank === 1) return { color: '#f0a500', fontWeight: 700 }
  if (rank === 2) return { color: '#9aa5b1', fontWeight: 700 }
  if (rank === 3) return { color: '#c07d3a', fontWeight: 700 }
  return { color: '#8b949e' }
}

const rankIcon = (rank) => {
  if (rank === 1) return '🥇'
  if (rank === 2) return '🥈'
  if (rank === 3) return '🥉'
  return `#${rank}`
}

const scoreColor = (score) => {
  if (score >= 90) return '#3fb950'
  if (score >= 80) return '#58a6ff'
  if (score >= 70) return '#d29922'
  return '#f85149'
}

export default function Leaderboard() {
  return (
    <section style={styles.section}>
      <h2 style={styles.heading}>Composite Leaderboard</h2>
      <p style={styles.sub}>Equal-weight average across {benchmarks.length} benchmarks</p>
      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={{ ...styles.th, width: 56 }}>Rank</th>
              <th style={styles.th}>Model</th>
              <th style={styles.th}>Org</th>
              <th style={{ ...styles.th, textAlign: 'right' }}>Composite</th>
              {benchmarks.map((b) => (
                <th key={b.id} style={{ ...styles.th, textAlign: 'right', whiteSpace: 'nowrap' }}>{b.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {leaderboardData.map((model) => (
              <tr key={model.id} style={styles.tr}>
                <td style={{ ...styles.td, textAlign: 'center', ...rankStyle(model.rank) }}>
                  {rankIcon(model.rank)}
                </td>
                <td style={styles.td}>
                  <span style={{ ...styles.dot, background: model.color }} />
                  <span style={{ fontWeight: 600, color: '#e6edf3' }}>{model.name}</span>
                </td>
                <td style={{ ...styles.td, color: '#8b949e' }}>{model.org}</td>
                <td style={{ ...styles.td, textAlign: 'right' }}>
                  <span style={{
                    ...styles.badge,
                    background: scoreColor(model.composite) + '22',
                    color: scoreColor(model.composite),
                    borderColor: scoreColor(model.composite) + '55',
                  }}>
                    {model.composite}
                  </span>
                </td>
                {benchmarks.map((b) => {
                  const s = b.scores[model.id]
                  return (
                    <td key={b.id} style={{ ...styles.td, textAlign: 'right', color: scoreColor(s) }}>
                      {s?.toFixed(1)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

const styles = {
  section: {
    background: '#161b22',
    border: '1px solid #30363d',
    borderRadius: 12,
    padding: '24px',
    marginBottom: 32,
  },
  heading: {
    fontSize: 18,
    fontWeight: 700,
    color: '#e6edf3',
    marginBottom: 4,
  },
  sub: {
    fontSize: 13,
    color: '#8b949e',
    marginBottom: 20,
  },
  tableWrap: {
    overflowX: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 13,
  },
  th: {
    padding: '8px 12px',
    textAlign: 'left',
    color: '#8b949e',
    fontWeight: 600,
    borderBottom: '1px solid #30363d',
    whiteSpace: 'nowrap',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  tr: {
    borderBottom: '1px solid #21262d',
    transition: 'background 0.15s',
  },
  td: {
    padding: '10px 12px',
    verticalAlign: 'middle',
  },
  dot: {
    display: 'inline-block',
    width: 8,
    height: 8,
    borderRadius: '50%',
    marginRight: 8,
    verticalAlign: 'middle',
  },
  badge: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 6,
    border: '1px solid',
    fontWeight: 700,
    fontSize: 13,
  },
}
