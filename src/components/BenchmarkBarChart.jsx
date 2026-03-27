import React, { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import { benchmarks, models } from '../data/benchmarks.js'

const COLORS = models.reduce((acc, m) => { acc[m.id] = m.color; return acc }, {})

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={ttStyle}>
      <div style={{ fontWeight: 700, marginBottom: 4, color: '#e6edf3' }}>{d.name}</div>
      <div style={{ color: '#58a6ff', fontSize: 20, fontWeight: 700 }}>{d.score.toFixed(1)}</div>
      <div style={{ color: '#8b949e', fontSize: 12 }}>{d.org}</div>
    </div>
  )
}

const ttStyle = {
  background: '#21262d',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: '10px 14px',
  fontSize: 13,
}

export default function BenchmarkBarChart() {
  const [selected, setSelected] = useState(benchmarks[0].id)

  const benchmark = benchmarks.find((b) => b.id === selected)

  const data = models
    .map((m) => ({
      id: m.id,
      name: m.name,
      org: m.org,
      score: benchmark.scores[m.id] ?? 0,
      color: m.color,
    }))
    .sort((a, b) => b.score - a.score)

  return (
    <section style={styles.section}>
      <div style={styles.header}>
        <div>
          <h2 style={styles.heading}>Benchmark Comparison</h2>
          <p style={styles.sub}>{benchmark.description}</p>
        </div>
        <div style={styles.selectorWrap}>
          {benchmarks.map((b) => (
            <button
              key={b.id}
              onClick={() => setSelected(b.id)}
              style={{
                ...styles.btn,
                ...(selected === b.id ? styles.btnActive : {}),
              }}
            >
              {b.name}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 16, right: 24, left: 0, bottom: 8 }} barCategoryGap="30%">
          <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: '#8b949e', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            interval={0}
            angle={-20}
            textAnchor="end"
            height={52}
          />
          <YAxis
            domain={[50, 100]}
            tick={{ fill: '#8b949e', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: '#ffffff0a' }} />
          <Bar dataKey="score" radius={[6, 6, 0, 0]} maxBarSize={56}>
            {data.map((entry) => (
              <Cell key={entry.id} fill={entry.color} fillOpacity={0.85} />
            ))}
            <LabelList
              dataKey="score"
              position="top"
              formatter={(v) => v.toFixed(1)}
              style={{ fill: '#8b949e', fontSize: 11 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
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
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    gap: 16,
    marginBottom: 24,
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
    maxWidth: 420,
  },
  selectorWrap: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
  },
  btn: {
    background: '#21262d',
    border: '1px solid #30363d',
    borderRadius: 6,
    color: '#8b949e',
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 500,
    padding: '4px 10px',
    transition: 'all 0.15s',
  },
  btnActive: {
    background: '#1f3a5c',
    border: '1px solid #58a6ff',
    color: '#58a6ff',
  },
}
