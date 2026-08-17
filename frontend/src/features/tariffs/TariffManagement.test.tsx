import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TariffManagement } from './TariffManagement'
import * as tariffApi from './api'
import { Tariff, TariffPage } from './api'

vi.mock('./api', async (importOriginal) => {
  const original = await importOriginal<typeof import('./api')>()
  return {
    ...original,
    deleteTariff: vi.fn(),
    getTariff: vi.fn(),
    getTariffVersions: vi.fn(),
    listTariffs: vi.fn(),
    updateTariff: vi.fn(),
    uploadTariff: vi.fn(),
  }
})

const TARIFF: Tariff = {
  id: '11111111-1111-1111-1111-111111111111',
  original_filename: 'Tabela-2026.pdf',
  internal_filename: 'internal.pdf',
  extension: '.pdf',
  mime_type: 'application/pdf',
  size: 2048,
  sha256: 'a'.repeat(64),
  description: 'Tabela vigente',
  notes: 'Conferida',
  active: true,
  version: 1,
  version_group_id: '22222222-2222-2222-2222-222222222222',
  previous_version_id: null,
  uploaded_by_id: '33333333-3333-3333-3333-333333333333',
  created_at: '2026-08-17T12:00:00Z',
  updated_at: '2026-08-17T12:00:00Z',
  deleted_at: null,
  usage_count: 0,
}

const PAGE: TariffPage = { items: [TARIFF], page: 1, page_size: 25, total: 1, pages: 1 }

describe('TariffManagement', () => {
  beforeEach(() => {
    vi.mocked(tariffApi.listTariffs).mockResolvedValue(PAGE)
    vi.mocked(tariffApi.getTariff).mockResolvedValue(TARIFF)
    vi.mocked(tariffApi.getTariffVersions).mockResolvedValue([TARIFF])
    vi.mocked(tariffApi.updateTariff).mockImplementation(async (_, patch) => ({
      ...TARIFF,
      ...patch,
    }))
    vi.mocked(tariffApi.uploadTariff).mockResolvedValue(TARIFF)
    vi.mocked(tariffApi.deleteTariff).mockResolvedValue()
  })

  it('completes upload, edit, download and deactivation as an operator', async () => {
    const user = userEvent.setup()
    render(<TariffManagement role="OPERATOR" />)

    expect(await screen.findByText('Tabela-2026.pdf')).toBeInTheDocument()
    const upload = screen.getByLabelText('Arquivos de tarifário')
    await user.upload(upload, new File(['region,price'], 'nova.csv', { type: 'text/csv' }))
    await user.click(screen.getByRole('button', { name: 'Enviar arquivos' }))
    expect(await screen.findByText('1 de 1 arquivo(s) enviado(s).')).toBeInTheDocument()
    expect(screen.getByText('nova.csv: concluído')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Detalhes' }))
    expect(await screen.findByText('Nenhuma auditoria relacionada disponível')).toBeInTheDocument()
    const download = screen.getByRole('link', { name: 'Baixar original' })
    expect(download).toHaveAttribute('href', `/api/tariffs/${TARIFF.id}/download`)

    const description = screen.getByLabelText('Descrição')
    await user.clear(description)
    await user.type(description, 'Nova descrição')
    await user.click(screen.getByRole('button', { name: 'Salvar metadata' }))
    await waitFor(() => expect(tariffApi.updateTariff).toHaveBeenCalledWith(
      TARIFF.id,
      { description: 'Nova descrição', notes: 'Conferida' },
    ))

    await user.click(screen.getByRole('button', { name: 'Desativar' }))
    await waitFor(() => expect(tariffApi.updateTariff).toHaveBeenCalledWith(
      TARIFF.id,
      { active: false },
    ))
  })

  it('shows per-file validation feedback and aggregate progress', async () => {
    const user = userEvent.setup({ applyAccept: false })
    vi.mocked(tariffApi.uploadTariff)
      .mockResolvedValueOnce(TARIFF)
      .mockRejectedValueOnce(new Error('file extension is not supported'))
    render(<TariffManagement role="ADMIN" />)

    await screen.findByText('Tabela-2026.pdf')
    await user.upload(screen.getByLabelText('Arquivos de tarifário'), [
      new File(['ok'], 'ok.csv', { type: 'text/csv' }),
      new File(['bad'], 'bad.exe', { type: 'application/octet-stream' }),
    ])
    await user.click(screen.getByRole('button', { name: 'Enviar arquivos' }))

    expect(await screen.findByText('1 de 2 arquivo(s) enviado(s).')).toBeInTheDocument()
    expect(screen.getByText('100% concluído')).toBeInTheDocument()
    expect(screen.getByText('bad.exe: file extension is not supported')).toHaveClass('error')
  })

  it('keeps viewer access read-only while preserving detail and download', async () => {
    const user = userEvent.setup()
    render(<TariffManagement role="VIEWER" />)

    expect(await screen.findByText('Tabela-2026.pdf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enviar arquivos' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Detalhes' }))
    expect(await screen.findByRole('link', { name: 'Baixar original' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Salvar metadata' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Desativar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remover' })).not.toBeInTheDocument()
  })

  it('soft deletes only after confirmation', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<TariffManagement role="ADMIN" />)

    await screen.findByText('Tabela-2026.pdf')
    await user.click(screen.getByRole('button', { name: 'Detalhes' }))
    await user.click(await screen.findByRole('button', { name: 'Remover' }))

    await waitFor(() => expect(tariffApi.deleteTariff).toHaveBeenCalledWith(TARIFF.id))
    expect(screen.getByText(/arquivo original foi preservado/i)).toBeInTheDocument()
  })
})
