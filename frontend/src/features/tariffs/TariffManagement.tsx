import { FormEvent, useCallback, useEffect, useState } from 'react'

import {
  deleteTariff,
  getTariff,
  getTariffVersions,
  listTariffs,
  Tariff,
  TariffFilters,
  TariffPage,
  updateTariff,
  uploadTariff,
} from './api'

type Role = 'ADMIN' | 'OPERATOR' | 'VIEWER'
type UploadState = { name: string; status: 'pending' | 'uploading' | 'done' | 'error'; error?: string }

const EMPTY_PAGE: TariffPage = { items: [], page: 1, page_size: 25, total: 0, pages: 0 }
const INITIAL_FILTERS: TariffFilters = { page: 1, pageSize: 25, search: '', active: '' }

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Não foi possível concluir a solicitação.'
}

function bytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function date(value: string): string {
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(value),
  )
}

export function TariffManagement({ role }: { role: Role }) {
  const canWrite = role !== 'VIEWER'
  const [filters, setFilters] = useState<TariffFilters>(INITIAL_FILTERS)
  const [draftSearch, setDraftSearch] = useState('')
  const [page, setPage] = useState<TariffPage>(EMPTY_PAGE)
  const [selected, setSelected] = useState<Tariff | null>(null)
  const [versions, setVersions] = useState<Tariff[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [uploads, setUploads] = useState<UploadState[]>([])
  const [description, setDescription] = useState('')
  const [notes, setNotes] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setPage(await listTariffs(filters))
    } catch (requestError) {
      setError(message(requestError))
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => void load(), [load])

  async function openDetail(tariff: Tariff) {
    setError('')
    try {
      const [detail, lineage] = await Promise.all([getTariff(tariff.id), getTariffVersions(tariff.id)])
      setSelected(detail)
      setVersions(lineage)
      setDescription(detail.description ?? '')
      setNotes(detail.notes ?? '')
    } catch (requestError) {
      setError(message(requestError))
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFilters((current) => ({ ...current, page: 1, search: draftSearch }))
  }

  async function submitFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const input = event.currentTarget.elements.namedItem('tariff-files') as HTMLInputElement
    const files = Array.from(input.files ?? [])
    if (!files.length) {
      setError('Selecione pelo menos um arquivo de tarifário.')
      return
    }
    setError('')
    setNotice('')
    setUploads(files.map((file) => ({ name: file.name, status: 'pending' })))
    let succeeded = 0
    for (const [index, file] of files.entries()) {
      setUploads((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: 'uploading' } : item))
      try {
        await uploadTariff(file)
        succeeded += 1
        setUploads((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: 'done' } : item))
      } catch (requestError) {
        setUploads((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: 'error', error: message(requestError) } : item))
      }
    }
    input.value = ''
    setNotice(`${succeeded} de ${files.length} arquivo(s) enviado(s).`)
    await load()
  }

  async function saveMetadata(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return
    setError('')
    try {
      const updated = await updateTariff(selected.id, {
        description: description.trim() || null,
        notes: notes.trim() || null,
      })
      setSelected(updated)
      setNotice('Descrição e observação atualizadas.')
      await load()
    } catch (requestError) {
      setError(message(requestError))
    }
  }

  async function toggleActive() {
    if (!selected) return
    setError('')
    try {
      const updated = await updateTariff(selected.id, { active: !selected.active })
      setSelected(updated)
      setNotice(updated.active ? 'Tarifário ativado.' : 'Tarifário desativado.')
      await load()
    } catch (requestError) {
      setError(message(requestError))
    }
  }

  async function remove() {
    if (!selected || !window.confirm('Ocultar este tarifário do catálogo ativo? O original será preservado.')) return
    setError('')
    try {
      await deleteTariff(selected.id)
      setSelected(null)
      setVersions([])
      setNotice('Tarifário removido logicamente; o arquivo original foi preservado.')
      await load()
    } catch (requestError) {
      setError(message(requestError))
    }
  }

  const completedUploads = uploads.filter((item) => item.status === 'done' || item.status === 'error').length
  const progress = uploads.length ? Math.round((completedUploads / uploads.length) * 100) : 0

  return (
    <section className="tariff-workspace" aria-labelledby="tariff-title">
      <header className="page-header">
        <div><p className="eyebrow">Catálogo</p><h1 id="tariff-title">Tarifários</h1><p>Originais imutáveis, versões rastreáveis e seleção sem vínculo fixo com parceiros.</p></div>
        <span className="role-badge">{role}</span>
      </header>

      {error && <p className="feedback error" role="alert">{error}</p>}
      {notice && <p className="feedback success" role="status">{notice}</p>}

      {canWrite && (
        <form className="upload-panel" onSubmit={(event) => void submitFiles(event)}>
          <div><h2>Enviar tarifários</h2><p>PDF, XLSX, XLS, CSV, PNG, JPEG ou TIFF. Cada arquivo gera um original independente.</p></div>
          <input aria-label="Arquivos de tarifário" name="tariff-files" type="file" multiple accept=".pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.tif,.tiff" />
          <button type="submit">Enviar arquivos</button>
          {uploads.length > 0 && <div className="upload-progress"><progress max="100" value={progress}>{progress}%</progress><span>{progress}% concluído</span><ul>{uploads.map((item, index) => <li key={`${item.name}-${index}`} className={item.status}>{item.name}: {item.status === 'pending' ? 'aguardando' : item.status === 'uploading' ? 'enviando' : item.status === 'done' ? 'concluído' : item.error}</li>)}</ul></div>}
        </form>
      )}

      <form className="filters" onSubmit={applyFilters}>
        <label>Buscar<input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} placeholder="Nome, descrição ou observação" /></label>
        <label>Status<select value={filters.active} onChange={(event) => setFilters((current) => ({ ...current, page: 1, active: event.target.value as TariffFilters['active'] }))}><option value="">Todos</option><option value="true">Ativos</option><option value="false">Inativos</option></select></label>
        <button type="submit">Aplicar filtros</button>
      </form>

      <div className="catalog-layout">
        <div className="catalog-card">
          <div className="section-heading"><h2>Arquivos</h2><span>{page.total} resultado(s)</span></div>
          {loading ? <p>Carregando catálogo…</p> : page.items.length === 0 ? <p>Nenhum tarifário encontrado.</p> : <div className="table-scroll"><table><thead><tr><th>Arquivo</th><th>Versão</th><th>Status</th><th>Descrição</th><th></th></tr></thead><tbody>{page.items.map((tariff) => <tr key={tariff.id}><td><strong>{tariff.original_filename}</strong><small>{bytes(tariff.size)} · {tariff.extension.slice(1).toUpperCase()}</small></td><td>v{tariff.version}</td><td><span className={`status-pill ${tariff.active ? 'active' : 'inactive'}`}>{tariff.active ? 'Ativo' : 'Inativo'}</span></td><td>{tariff.description || '—'}</td><td><button className="secondary" type="button" onClick={() => void openDetail(tariff)}>Detalhes</button></td></tr>)}</tbody></table></div>}
          <nav className="pagination" aria-label="Paginação"><button className="secondary" type="button" disabled={page.page <= 1} onClick={() => setFilters((current) => ({ ...current, page: current.page - 1 }))}>Anterior</button><span>Página {page.page} de {Math.max(page.pages, 1)}</span><button className="secondary" type="button" disabled={page.pages === 0 || page.page >= page.pages} onClick={() => setFilters((current) => ({ ...current, page: current.page + 1 }))}>Próxima</button></nav>
        </div>

        <aside className="detail-card" aria-live="polite">
          {!selected ? <div className="empty-detail"><h2>Detalhes</h2><p>Selecione um arquivo para ver integridade, versões e ações.</p></div> : <><div className="section-heading"><div><h2>{selected.original_filename}</h2><p>Versão {selected.version} · enviado em {date(selected.created_at)}</p></div><span className={`status-pill ${selected.active ? 'active' : 'inactive'}`}>{selected.active ? 'Ativo' : 'Inativo'}</span></div><dl><div><dt>SHA-256</dt><dd className="hash">{selected.sha256}</dd></div><div><dt>Tipo e tamanho</dt><dd>{selected.mime_type} · {bytes(selected.size)}</dd></div><div><dt>Uso em auditorias</dt><dd>{selected.usage_count ? `${selected.usage_count} auditoria(s)` : 'Nenhuma auditoria relacionada disponível'}</dd></div></dl><a className="button-link" href={`/api/tariffs/${selected.id}/download`}>Baixar original</a>{canWrite && <><form className="metadata-form" onSubmit={(event) => void saveMetadata(event)}><label>Descrição<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={4000} /></label><label>Observação<textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={4000} /></label><button type="submit">Salvar metadata</button></form><div className="detail-actions"><button className="secondary" type="button" onClick={() => void toggleActive()}>{selected.active ? 'Desativar' : 'Ativar'}</button><button className="danger" type="button" onClick={() => void remove()}>Remover</button></div></>}<div className="version-list"><h3>Histórico de versões</h3><ol>{versions.map((version) => <li key={version.id}>v{version.version} · {version.original_filename} · {date(version.created_at)}</li>)}</ol></div></>}
        </aside>
      </div>
    </section>
  )
}
