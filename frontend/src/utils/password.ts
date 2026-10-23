/** Client-side mirror of the backend password policy (app/core/security.py). */
export function passwordChecks(password: string, email = ''): { label: string; ok: boolean }[] {
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(password)).length
  const local = email.split('@')[0]?.toLowerCase() ?? ''
  return [
    { label: 'At least 10 characters', ok: password.length >= 10 && password.length <= 128 },
    { label: 'Three of: lowercase, uppercase, digit, symbol', ok: classes >= 3 },
    { label: 'Does not contain your email name', ok: local.length < 4 || !password.toLowerCase().includes(local) },
  ]
}
