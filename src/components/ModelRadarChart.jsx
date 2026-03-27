import React, { useState } from 'react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { benchmarks, models } from '../data/benchmarks.js'

const MAX_SELECTED = 4

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={ttStyle}>
      <div style={{ fontWeight: 700, marginBottom: 6, color: '#e6edf3' }}>
        {payload[0]?.payload?.benchmark}
      </div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color, marginBottom: 2 }}>
          {p.name}: <strong>{p.value?.toFixed(1)}</strong>
        </div>
      ))}
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

export default function ModelRadarChart() {
  const [selected, setSelected] = useState(['gpt4o', 'claude35s', 'gemini15p'])

  const toggle = (id) => {
    setSelected((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : prev.length < MAX_SELECTED
        ? [...prev, id]
        : prev
    )
  }

  const data = benchmarks.map((b) => {
    const entry = { benchmark: b.name }
    selected.forEach((id) => { entry[id] = b.scores[id] ?? 0 })
    return entry
  })

  return (
    <section style={styles.section}>
      <div style={styles.header}>
        <div>
          <h2 style={styles.heading}>Capability Radar</h2>
          <p style={styles.sub}>Select up to {MAX_SELECTED} models to compare across all benchmarks</p>
        </div>
        <div style={styles.modelButtons}>
          {models.map((m) => {
            const active = selected.includes(m.id)
            const disabled = !active && selected.length >= MAX_SELECTED
            return (
              <button
                key={m.id}
                onClick={() => toggle(m.id)}
                disabled={disabled}
                style={{
                  ...styles.modelBtn,
                  borderColor: active ? m.color : '#30363d',
                  background: active ? m.color + '22' : '#21262d',
                  color: active ? m.color : '#8b949e',
                  opacity: disabled ? 0.4 : 1,
                  cursor: disabled ? 'not-allowed' : 'pointer',
                }}
              >
                <span style={{ ...styles.dot, background: active ? m.color : '#30363d' }} />
                {m.name}
              </button>
            )
          })}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={400}>
        <RadarChart data={data} margin={{ top: 16, right: 32, bottom: 16, left: 32 }}>
          <PolarGrid stroke="#30363d" />
          <PolarAngleAxis
            dataKey="benchmark"
            tick={{ fill: '#8b949e', fontSize: 12 }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[50, 100]}
            tick={{ fill: '#8b949e', fontSize: 10 }}
            tickCount={4}
            axisLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          {selected.map((id) => {
            const model = models.find((m) => m.id === id)
            return (
              <Radar
                key={id}
                name={model?.name ?? id}
                dataKey={id}
                stroke={model?.color}
                fill={model?.color}
                fillOpacity={0.12}
                strokeWidth={2}
                dot={{ r: 3, fill: model?.color }}
              />
            )
          })}
          <Legend
            wrapperStyle={{ fontSize: 12, color: '#8b949e', paddingTop: 8 }}
            formatter={(value) => <span style={{ color: '#8b949e' }}>{value}</span>}
          />
        </RadarChart>
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
  },
  modelButtons: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
  },
  modelBtn: {
    border: '1px solid',
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 500,
    padding: '4px 10px',
    transition: 'all 0.15s',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: '50%',
    display: 'inline-block',
    flexShrink: 0,
  },
}
