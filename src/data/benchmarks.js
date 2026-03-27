export const models = [
  { id: 'gpt4o',        name: 'GPT-4o',             org: 'OpenAI',    color: '#10a37f' },
  { id: 'claude35s',    name: 'Claude 3.5 Sonnet',  org: 'Anthropic', color: '#d97706' },
  { id: 'gemini15p',    name: 'Gemini 1.5 Pro',     org: 'Google',    color: '#4285f4' },
  { id: 'llama31_405b', name: 'Llama 3.1 405B',     org: 'Meta',      color: '#0668e1' },
  { id: 'grok2',        name: 'Grok-2',             org: 'xAI',       color: '#ffffff' },
  { id: 'mistralL2',    name: 'Mistral Large 2',    org: 'Mistral',   color: '#ff7000' },
  { id: 'deepseekv25',  name: 'DeepSeek V2.5',      org: 'DeepSeek',  color: '#3b82f6' },
  { id: 'commandrp',    name: 'Command R+',         org: 'Cohere',    color: '#39d353' },
]

// Scores are 0-100 (percentage or normalized)
export const benchmarks = [
  {
    id: 'mmlu',
    name: 'MMLU',
    description: 'Massive Multitask Language Understanding — knowledge across 57 subjects',
    scores: {
      gpt4o:        88.7,
      claude35s:    88.3,
      gemini15p:    85.9,
      llama31_405b: 88.6,
      grok2:        87.5,
      mistralL2:    84.0,
      deepseekv25:  80.4,
      commandrp:    75.7,
    },
  },
  {
    id: 'humaneval',
    name: 'HumanEval',
    description: 'Python coding problems — pass@1 accuracy',
    scores: {
      gpt4o:        90.2,
      claude35s:    92.0,
      gemini15p:    84.1,
      llama31_405b: 89.0,
      grok2:        88.4,
      mistralL2:    92.1,
      deepseekv25:  89.0,
      commandrp:    71.7,
    },
  },
  {
    id: 'math',
    name: 'MATH',
    description: 'Competition-level math problem solving',
    scores: {
      gpt4o:        76.6,
      claude35s:    71.1,
      gemini15p:    67.7,
      llama31_405b: 73.8,
      grok2:        76.1,
      mistralL2:    69.3,
      deepseekv25:  74.7,
      commandrp:    50.0,
    },
  },
  {
    id: 'gsm8k',
    name: 'GSM8K',
    description: 'Grade-school math word problems',
    scores: {
      gpt4o:        95.8,
      claude35s:    96.4,
      gemini15p:    90.8,
      llama31_405b: 96.8,
      grok2:        94.2,
      mistralL2:    93.0,
      deepseekv25:  92.2,
      commandrp:    88.2,
    },
  },
  {
    id: 'hellaswag',
    name: 'HellaSwag',
    description: 'Commonsense NLI — 10-shot evaluation',
    scores: {
      gpt4o:        95.3,
      claude35s:    89.0,
      gemini15p:    92.5,
      llama31_405b: 89.1,
      grok2:        87.3,
      mistralL2:    88.7,
      deepseekv25:  87.8,
      commandrp:    85.1,
    },
  },
  {
    id: 'arc_c',
    name: 'ARC-Challenge',
    description: 'Science questions requiring reasoning beyond pattern matching',
    scores: {
      gpt4o:        96.4,
      claude35s:    93.1,
      gemini15p:    91.4,
      llama31_405b: 96.9,
      grok2:        94.5,
      mistralL2:    92.7,
      deepseekv25:  89.3,
      commandrp:    84.3,
    },
  },
  {
    id: 'truthfulqa',
    name: 'TruthfulQA',
    description: 'Truthfulness — avoidance of common misconceptions',
    scores: {
      gpt4o:        77.4,
      claude35s:    82.4,
      gemini15p:    76.1,
      llama31_405b: 73.0,
      grok2:        72.8,
      mistralL2:    69.6,
      deepseekv25:  68.4,
      commandrp:    65.0,
    },
  },
  {
    id: 'bbh',
    name: 'BIG-Bench Hard',
    description: 'Diverse challenging tasks requiring multi-step reasoning',
    scores: {
      gpt4o:        83.1,
      claude35s:    84.0,
      gemini15p:    75.0,
      llama31_405b: 81.6,
      grok2:        80.1,
      mistralL2:    78.2,
      deepseekv25:  79.7,
      commandrp:    66.5,
    },
  },
]

// Compute composite score (equal weight average across all benchmarks)
export function computeComposite(modelId) {
  const total = benchmarks.reduce((sum, b) => sum + (b.scores[modelId] ?? 0), 0)
  return +(total / benchmarks.length).toFixed(1)
}

export const leaderboardData = models
  .map((m) => ({ ...m, composite: computeComposite(m.id) }))
  .sort((a, b) => b.composite - a.composite)
  .map((m, i) => ({ ...m, rank: i + 1 }))
