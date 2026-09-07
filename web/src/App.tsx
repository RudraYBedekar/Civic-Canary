import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Check,
  Clock3,
  FileCheck2,
  KeyRound,
  Play,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react'

import { api, type Finding, type Run, type Target } from './api'
import './styles.css'

function formatTime(value: string | null) {
  if (!value) return 'Not completed'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export default function App() {
  const [target, setTarget] = useState<Target | null>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [token, setToken] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    const [targetRows, runRows, findingRows] = await Promise.all([
      api.targets(),
      api.runs(),
      api.findings(),
    ])
    setTarget(targetRows[0] ?? null)
    setRuns(runRows)
    setFindings(findingRows)
    setSelectedFinding((current) =>
      current ? findingRows.find((item) => item.finding_id === current.finding_id) ?? null : null,
    )
  }

  useEffect(() => {
    // The asynchronous load synchronizes the dashboard with the external API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load().catch((reason: Error) => setError(reason.message))
  }, [])

  const openFindings = useMemo(
    () => findings.filter((finding) => finding.status === 'OPEN'),
    [findings],
  )

  const act = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await operation()
      await load()
      setMessage(success)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const setVersion = (version: 'v1' | 'v2') =>
    act(() => api.setVersion(version, token), `Demo portal switched to ${version.toUpperCase()}.`)

  const runScan = async () => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const started = await api.startRun(token)
      let run = started.run
      for (let attempt = 0; run.status === 'QUEUED' || run.status === 'RUNNING'; attempt += 1) {
        if (attempt >= 150) throw new Error('The scan is still running. Check the audit trail shortly.')
        await new Promise((resolve) => window.setTimeout(resolve, 2000))
        run = await api.run(run.run_id)
      }
      await load()
      if (run.status === 'FAILED') throw new Error(run.summary || 'The scan failed.')
      setMessage('Scan complete. Findings are ready for review.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const decide = (action: 'APPROVE' | 'REJECT') => {
    if (!selectedFinding) return
    void act(
      () => api.decide(selectedFinding.finding_id, action, note, token),
      action === 'APPROVE'
        ? 'Approved draft created. No public content was changed.'
        : 'Finding rejected.',
    )
    setNote('')
  }

  const openFinding = async (finding: Finding) => {
    setSelectedFinding(finding)
    try {
      setSelectedFinding(await api.finding(finding.finding_id))
    } catch {
      // The list payload remains useful if a short-lived evidence URL cannot be issued.
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="identity" href="#dashboard" aria-label="Civic Canary dashboard">
          <span className="mark"><Activity aria-hidden="true" /></span>
          <span><strong>Civic Canary</strong><small>Quiet monitoring for public-service changes</small></span>
        </a>
        <div className="safety"><ShieldCheck aria-hidden="true" /> Read-only monitoring</div>
      </header>

      <main id="dashboard">
        <section className="hero">
          <div>
            <p className="kicker">River County benefits</p>
            <h1>Only surface changes that matter.</h1>
            <p className="lede">Civic Canary checks the portal in the background, traces the impact on community guidance, and leaves every consequential decision to a person.</p>
          </div>
          <div className="hero-status" aria-label="Current target status">
            <span className="pulse" aria-hidden="true" />
            <div><small>Monitoring</small><strong>{target?.name ?? 'Loading target…'}</strong></div>
          </div>
        </section>

        <section className="metrics" aria-label="Summary">
          <article><small>Open decisions</small><strong>{openFindings.length}</strong><span>Need a human</span></article>
          <article><small>Latest run</small><strong>{runs[0]?.status ?? '—'}</strong><span>{formatTime(runs[0]?.finished_at ?? null)}</span></article>
          <article><small>Portal version</small><strong>{target?.active_version.toUpperCase() ?? '—'}</strong><span>Synthetic demo</span></article>
        </section>

        <section className="work-grid">
          <div className="primary-column">
            <div className="section-heading">
              <div><p className="kicker">Decision queue</p><h2>Material findings</h2></div>
              <button className="secondary-button" onClick={() => void load()} aria-label="Refresh data"><RefreshCw aria-hidden="true" /> Refresh</button>
            </div>

            <div className="finding-list">
              {findings.length === 0 ? (
                <div className="empty-state"><FileCheck2 aria-hidden="true" /><h3>No findings yet</h3><p>Switch to V2 and run a scan to reveal the controlled regressions.</p></div>
              ) : findings.map((finding) => (
                <button className="finding-card" key={finding.finding_id} onClick={() => void openFinding(finding)}>
                  <span className={`severity severity-${finding.severity.toLowerCase()}`}>{finding.severity}</span>
                  <span className="finding-copy"><strong>{finding.title}</strong><small>{finding.category.replace('_', ' ')} · {finding.affected_playbook_sections.join(', ')}</small></span>
                  <span className={`finding-state state-${finding.status.toLowerCase()}`}>{finding.status}</span>
                  <ArrowRight aria-hidden="true" />
                </button>
              ))}
            </div>

            <div className="section-heading runs-heading">
              <div><p className="kicker">Audit trail</p><h2>Recent runs</h2></div>
            </div>
            <div className="run-list">
              {runs.map((run) => (
                <button key={run.run_id} className="run-row" onClick={() => setSelectedRun(run)}>
                  <span className="run-icon"><Clock3 aria-hidden="true" /></span>
                  <span><strong>{run.trigger_type.toLowerCase()} scan</strong><small>{formatTime(run.finished_at)}</small></span>
                  <span className={`run-status status-${run.status.toLowerCase()}`}>{run.status}</span>
                </button>
              ))}
            </div>
          </div>

          <aside className="demo-panel">
            <p className="kicker">Demo controls</p>
            <h2>Simulate a portal change</h2>
            <p>V1 is the trusted baseline. V2 adds one document requirement, breaks Spanish guidance, and removes a form label.</p>

            <label htmlFor="review-token"><KeyRound aria-hidden="true" /> Review token</label>
            <input id="review-token" type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" placeholder="Required for actions" />
            <p className="privacy-note">Held in memory only—never saved in this browser.</p>

            <div className="version-switch" aria-label="Portal version">
              {(['v1', 'v2'] as const).map((version) => (
                <button key={version} className={target?.active_version === version ? 'active' : ''} disabled={!token || busy} onClick={() => void setVersion(version)}>
                  {version.toUpperCase()}
                </button>
              ))}
            </div>
            <button className="primary-button" disabled={!token || busy} onClick={() => void runScan()}>
              {busy ? <RefreshCw className="spin" aria-hidden="true" /> : <Play aria-hidden="true" />}
              {busy ? 'Working…' : 'Run Canary scan'}
            </button>
            <a className="portal-link" href={`/portal/${target?.active_version ?? 'v1'}/index.html`} target="_blank" rel="noreferrer">
              Open synthetic portal <ArrowRight aria-hidden="true" />
            </a>
          </aside>
        </section>

        <div className="announcements" aria-live="polite">
          {message && <p className="success-message"><Check aria-hidden="true" />{message}</p>}
          {error && <p className="error-message"><AlertTriangle aria-hidden="true" />{error}</p>}
        </div>
      </main>

      {selectedFinding && (
        <div className="drawer-backdrop" role="presentation" onMouseDown={() => setSelectedFinding(null)}>
          <section className="drawer" role="dialog" aria-modal="true" aria-labelledby="finding-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="close-button" onClick={() => setSelectedFinding(null)} aria-label="Close finding"><X aria-hidden="true" /></button>
            <span className={`severity severity-${selectedFinding.severity.toLowerCase()}`}>{selectedFinding.severity}</span>
            <h2 id="finding-title">{selectedFinding.title}</h2>
            <p className="drawer-meta">{selectedFinding.category.replace('_', ' ')} · {selectedFinding.status}</p>
            <h3>Observed evidence</h3>
            <ul>{selectedFinding.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
            {selectedFinding.screenshot_urls.map((url) => (
              <img className="evidence-image" key={url} src={url} alt="Portal captured during this finding's scan" />
            ))}
            <h3>Affected guidance</h3>
            <p>{selectedFinding.affected_playbook_sections.join(', ')}</p>
            <h3>Proposed patch</h3>
            <pre>{selectedFinding.proposed_patch}</pre>
            {selectedFinding.status === 'OPEN' && (
              <>
                <label htmlFor="decision-note">Reviewer note</label>
                <textarea id="decision-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Optional evidence or reason" />
                <div className="decision-actions">
                  <button className="secondary-button" disabled={!token || busy} onClick={() => decide('REJECT')}><X aria-hidden="true" /> Reject</button>
                  <button className="primary-button" disabled={!token || busy} onClick={() => decide('APPROVE')}><Check aria-hidden="true" /> Approve draft</button>
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {selectedRun && (
        <div className="drawer-backdrop" role="presentation" onMouseDown={() => setSelectedRun(null)}>
          <section className="drawer" role="dialog" aria-modal="true" aria-labelledby="run-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="close-button" onClick={() => setSelectedRun(null)} aria-label="Close run"><X aria-hidden="true" /></button>
            <p className="kicker">Run detail</p>
            <h2 id="run-title">{selectedRun.run_id}</h2>
            <p>{selectedRun.summary}</p>
            <div className="timeline">
              {selectedRun.node_timings.map((node) => (
                <div key={node.node}><Check aria-hidden="true" /><span><strong>{node.node.replaceAll('-', ' ')}</strong><small>{node.duration_ms} ms</small></span></div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
