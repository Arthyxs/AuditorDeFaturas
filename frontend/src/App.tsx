import { FormEvent, useEffect, useState } from 'react'

import { TariffManagement } from './features/tariffs/TariffManagement'
import { EmailReview } from './features/emails/EmailReview'

type User = { username: string; role: 'ADMIN' | 'OPERATOR' | 'VIEWER' }
type Mode = 'loading' | 'bootstrap' | 'login' | 'authenticated'

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!response.ok) throw new Error('Não foi possível concluir a solicitação.')
  return (await response.json()) as T
}

export function App() {
  const [mode, setMode] = useState<Mode>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const current = await api<User>('/api/auth/me')
        setUser(current)
        setMode('authenticated')
      } catch {
        const status = await api<{ available: boolean }>('/api/auth/bootstrap/status')
        setMode(status.available ? 'bootstrap' : 'login')
      }
    })()
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const values = new FormData(event.currentTarget)
    const endpoint = mode === 'bootstrap' ? '/api/auth/bootstrap' : '/api/auth/login'
    const payload: Record<string, string> = {
      username: String(values.get('username') ?? ''),
      password: String(values.get('password') ?? ''),
    }
    if (mode === 'bootstrap') payload.bootstrap_token = String(values.get('token') ?? '')
    try {
      const authenticated = await api<User>(endpoint, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setUser(authenticated)
      setMode('authenticated')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Falha de autenticação.')
    }
  }

  async function logout() {
    await api('/api/auth/logout', { method: 'POST', body: '{}' })
    setUser(null)
    setMode('login')
  }

  if (mode === 'loading') return <main className="app-shell"><p>Carregando…</p></main>

  if (mode === 'authenticated' && user) {
    return (
      <div className="authenticated-shell">
        <header className="topbar"><a className="brand" href="/">InvoiceAuditor</a><div><span>{user.username}</span><button className="secondary" type="button" onClick={() => void logout()}>Sair</button></div></header>
        <main className="content-shell">
          <EmailReview role={user.role} />
          <TariffManagement role={user.role} />
        </main>
      </div>
    )
  }

  return (
    <main className="app-shell">
      <section className="welcome-card" aria-labelledby="page-title">
        <p className="eyebrow">InvoiceAuditor</p>
        <h1 id="page-title">{mode === 'bootstrap' ? 'Criar primeiro administrador' : 'Entrar'}</h1>
        <p>{mode === 'bootstrap' ? 'Use o token único gerado pelo setup.' : 'Acesse com sua conta local.'}</p>
        <form onSubmit={(event) => void submit(event)}>
          <label>Usuário<input name="username" autoComplete="username" required minLength={3} /></label>
          <label>Senha<input name="password" type="password" autoComplete={mode === 'bootstrap' ? 'new-password' : 'current-password'} required minLength={mode === 'bootstrap' ? 12 : 1} /></label>
          {mode === 'bootstrap' && <label>Token de configuração<input name="token" type="password" autoComplete="off" required minLength={32} /></label>}
          {error && <p className="error" role="alert">{error}</p>}
          <button type="submit">{mode === 'bootstrap' ? 'Criar administrador' : 'Entrar'}</button>
        </form>
      </section>
    </main>
  )
}
