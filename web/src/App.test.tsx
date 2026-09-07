import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'

import App from './App'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.endsWith('/api/targets')
      ? [{ target_id: 'benefits-demo', name: 'River County Benefits Portal', active_version: 'v1', enabled: true }]
      : []
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
})

test('renders the decision dashboard without persisting a token', async () => {
  render(<App />)
  expect(await screen.findByText('River County Benefits Portal')).toBeInTheDocument()
  expect(screen.getByLabelText('Review token')).toHaveAttribute('type', 'password')
  expect(screen.getByRole('button', { name: /run canary scan/i })).toBeDisabled()
})

