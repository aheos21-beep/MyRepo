import React from 'react'
import Leaderboard from './components/Leaderboard.jsx'
import BenchmarkBarChart from './components/BenchmarkBarChart.jsx'
import ModelRadarChart from './components/ModelRadarChart.jsx'
import { benchmarks, models } from './data/benchmarks.js'

export default function App() {
  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <div style={styles.headerInner}>
          <div style={styles.logo}>
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" style={{ flexShrink: 0 }}>
              <rect width="28" height="28" rx="6" fill="#1f3a5c" />
              <rect x="5" y="16" width="4" height="7" rx="1" fill="#58a6ff" />
              <rect x="12" y="10" width="4" height="13" rx="1" fill="#58a6ff" opacity="0.8" />
              <rect x="19" y="5" width="4" height="18" rx="1" fill="#58a6ff" opacity="0.6" />
            </svg>
            <div>
              <div style={styles.title}>AI Benchmark Dashboard</div>
              <div style={styles.subtitle}>
                {models.length} models &nbsp;·&nbsp; {benchmarks.length} benchmarks &nbsp;·&nbsp; March 2026
              </div>
            </div>
          </div>
          <div style={styles.pills}>
            <span style={styles.pill}>Live Rankings</span>
            <span style={{ ...styles.pill, background: '#1a3a1a', borderColor: '#3fb95055', color: '#3fb950' }}>
              Open Source Included
            </span>
          </div>
        </div>
      </header>

      <main style={styles.main}>
        <Leaderboard />
        <div style={styles.grid}>
          <BenchmarkBarChart />
          <ModelRadarChart />
        </div>
      </main>

      <footer style={styles.footer}>
        <p>
          Scores sourced from official model cards and published evaluations. Composite = equal-weight mean.
        </p>
      </footer>
    </div>
  )
}

const styles = {
  app: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: '#0d1117',
  },
  header: {
    background: '#161b22',
    borderBottom: '1px solid #30363d',
    padding: '16px 24px',
    position: 'sticky',
    top: 0,
    zIndex: 10,
  },
  headerInner: {
    maxWidth: 1400,
    margin: '0 auto',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 16,
    flexWrap: 'wrap',
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },
  title: {
    fontSize: 17,
    fontWeight: 700,
    color: '#e6edf3',
    letterSpacing: '-0.01em',
  },
  subtitle: {
    fontSize: 12,
    color: '#8b949e',
    marginTop: 1,
  },
  pills: {
    display: 'flex',
    gap: 8,
    flexWrap: 'wrap',
  },
  pill: {
    fontSize: 11,
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: 20,
    border: '1px solid #1f3a5c',
    background: '#1f3a5c',
    color: '#58a6ff',
    letterSpacing: '0.02em',
  },
  main: {
    flex: 1,
    maxWidth: 1400,
    margin: '0 auto',
    width: '100%',
    padding: '32px 24px',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))',
    gap: 24,
  },
  footer: {
    borderTop: '1px solid #21262d',
    padding: '16px 24px',
    textAlign: 'center',
    color: '#8b949e',
    fontSize: 12,
  },
}
