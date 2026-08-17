import { useEffect, useState } from 'react'

import { apiRequest } from '../../api/client'

type Role = 'ADMIN' | 'OPERATOR' | 'VIEWER'
type Classification = 'INVOICE' | 'DUE_NOTICE' | 'GENERAL' | 'MANUAL_REVIEW'
type ReviewItem = {
  id: string
  confidence: string
  threshold: string
  partner_name: string | null
  summary: string
  evidence: string[]
  current_folder: string
}
type ReviewPage = { items: ReviewItem[]; total: number }

export function EmailReview({ role }: { role: Role }) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [error, setError] = useState('')
  const canReview = role !== 'VIEWER'

  async function load() {
    try {
      const page = await apiRequest<ReviewPage>('/api/emails/review?page=1&page_size=25')
      setItems(page.items)
      setError('')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Falha ao carregar revisões.')
    }
  }

  useEffect(() => {
    let active = true
    void apiRequest<ReviewPage>('/api/emails/review?page=1&page_size=25')
      .then((page) => {
        if (active) setItems(page.items)
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : 'Falha ao carregar revisões.')
        }
      })
    return () => { active = false }
  }, [])

  async function resolve(id: string, classification: Exclude<Classification, 'MANUAL_REVIEW'>) {
    try {
      await apiRequest(`/api/emails/${id}/review`, {
        method: 'PATCH',
        headers: { Origin: window.location.origin },
        body: JSON.stringify({ classification }),
      })
      await load()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Falha ao salvar revisão.')
    }
  }

  return (
    <section className="email-review" aria-labelledby="email-review-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Classificação</p>
          <h2 id="email-review-title">Revisão de e-mails</h2>
          <p>Baixa confiança nunca segue como fatura sem decisão explícita.</p>
        </div>
        <span className="role-badge">{items.length} pendente(s)</span>
      </div>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {items.length === 0 ? <p>Nenhum e-mail aguarda revisão.</p> : (
        <div className="review-grid">
          {items.map((item) => (
            <article className="catalog-card" key={item.id}>
              <strong>{item.partner_name ?? 'Parceiro não identificado'}</strong>
              <p>{item.summary}</p>
              <small>Confiança {item.confidence} · limiar {item.threshold} · {item.current_folder}</small>
              <ul>{item.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}</ul>
              {canReview && <div className="detail-actions">
                <button type="button" onClick={() => void resolve(item.id, 'INVOICE')}>Fatura</button>
                <button className="secondary" type="button" onClick={() => void resolve(item.id, 'DUE_NOTICE')}>Aviso</button>
                <button className="secondary" type="button" onClick={() => void resolve(item.id, 'GENERAL')}>Geral</button>
              </div>}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
