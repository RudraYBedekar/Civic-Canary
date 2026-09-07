export type Target = {
  target_id: string
  name: string
  active_version: 'v1' | 'v2'
  enabled: boolean
}

export type NodeTiming = {
  node: string
  duration_ms: number
  status: 'SUCCEEDED' | 'FAILED'
}

export type Run = {
  run_id: string
  target_id: string
  trigger_type: 'MANUAL' | 'SCHEDULED'
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  started_at: string | null
  finished_at: string | null
  node_timings: NodeTiming[]
  summary: string
  error_category: string | null
}

export type Finding = {
  finding_id: string
  run_id: string
  target_id: string
  title: string
  category: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH'
  materiality: 'COSMETIC' | 'MATERIAL' | 'NEEDS_REVIEW'
  evidence: string[]
  affected_playbook_sections: string[]
  proposed_patch: string
  evidence_urls: string[]
  screenshot_urls: string[]
  approved_artifact_key: string | null
  status: 'OPEN' | 'APPROVAL_PENDING' | 'APPROVED' | 'REJECTED'
  created_at: string
  decision_note: string | null
}

declare global {
  interface Window {
    CIVIC_CANARY_CONFIG?: { apiUrl?: string }
  }
}

const baseUrl = window.CIVIC_CANARY_CONFIG?.apiUrl ?? import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, init)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload.detail
    throw new Error(
      typeof detail === 'string'
        ? detail
        : detail?.message ?? `Request failed with status ${response.status}`,
    )
  }
  return payload as T
}

function protectedHeaders(token: string) {
  return {
    'Content-Type': 'application/json',
    'X-Review-Token': token,
  }
}

export const api = {
  targets: () => request<Target[]>('/api/targets'),
  runs: () => request<Run[]>('/api/runs'),
  run: (runId: string) => request<Run>(`/api/runs/${runId}`),
  findings: () => request<Finding[]>('/api/findings'),
  finding: (findingId: string) => request<Finding>(`/api/findings/${findingId}`),
  setVersion: (version: 'v1' | 'v2', token: string) =>
    request<Target>('/api/demo/version', {
      method: 'POST',
      headers: protectedHeaders(token),
      body: JSON.stringify({ target_id: 'benefits-demo', version }),
    }),
  startRun: (token: string) =>
    request<{ run: Run; findings: Finding[] }>('/api/runs', {
      method: 'POST',
      headers: protectedHeaders(token),
      body: JSON.stringify({ target_id: 'benefits-demo' }),
    }),
  decide: (findingId: string, action: 'APPROVE' | 'REJECT', note: string, token: string) =>
    request<{ finding: Finding; approved_artifact_key: string | null }>(
      `/api/findings/${findingId}/decision`,
      {
        method: 'POST',
        headers: protectedHeaders(token),
        body: JSON.stringify({ action, note }),
      },
    ),
}
