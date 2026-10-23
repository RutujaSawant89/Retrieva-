import { describe, expect, it } from 'vitest'

import { passwordChecks } from './password'

describe('passwordChecks', () => {
  it('accepts a password that satisfies the backend policy', () => {
    expect(passwordChecks('Sup3r-Secret-Pass!', 'ada@acme.example.com').every((c) => c.ok)).toBe(true)
  })

  it('flags short passwords and missing character classes', () => {
    const checks = passwordChecks('short', '')
    expect(checks[0].ok).toBe(false)
    expect(checks[1].ok).toBe(false)
  })

  it('rejects passwords containing the email local part', () => {
    expect(passwordChecks('Lovelace-2024!', 'lovelace@acme.example.com')[2].ok).toBe(false)
  })
})
