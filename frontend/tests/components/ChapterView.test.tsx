import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ChapterView } from '@/components/ChapterView'

vi.mock('@/api/client', () => ({
  api: {
    chapters: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    },
    sentences: {
      update: vi.fn(),
      create: vi.fn(),
      delete: vi.fn(),
    },
  },
}))

import { api } from '@/api/client'

const mockedApi = vi.mocked(api)

const mockDocument = {
  attrs: { id: 'd-1', title: 'Faith', author: 'Paul' },
  chapter_summaries: [],
}

describe('ChapterView', () => {
  const onBack = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.chapters.list.mockResolvedValue([])
  })

  it('shows a "New Chapter" button in the sidebar', async () => {
    render(<ChapterView document={mockDocument} onBack={onBack} />)

    expect(
      await screen.findByRole('button', { name: 'New Chapter' })
    ).toBeInTheDocument()
  })

  it('shows a title input form after clicking New Chapter', async () => {
    const user = userEvent.setup()
    render(<ChapterView document={mockDocument} onBack={onBack} />)

    await user.click(await screen.findByRole('button', { name: 'New Chapter' }))

    expect(screen.getByLabelText('Chapter Title')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Create' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Cancel' })
    ).toBeInTheDocument()
  })

  it('calls api.chapters.create with correct payload on submit', async () => {
    const user = userEvent.setup()
    mockedApi.chapters.create.mockResolvedValue({
      status: { code: 'ok', message: 'created' },
    })
    mockedApi.chapters.list.mockResolvedValue([])

    render(<ChapterView document={mockDocument} onBack={onBack} />)
    await user.click(await screen.findByRole('button', { name: 'New Chapter' }))

    await user.type(screen.getByLabelText('Chapter Title'), 'Introduction')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(mockedApi.chapters.create).toHaveBeenCalledOnce()
    })

    const callArgs = mockedApi.chapters.create.mock.calls[0][0]
    expect(callArgs.attrs.title).toBe('Introduction')
    expect(callArgs.relations.document_id).toBe('d-1')
    expect(callArgs.attrs.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    )
  })

  it('refreshes chapter list and opens editor after successful creation', async () => {
    const user = userEvent.setup()
    mockedApi.chapters.create.mockResolvedValue({
      status: { code: 'ok', message: 'created' },
    })
    mockedApi.chapters.list
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: 'ch-1', title: 'Introduction' }])
    mockedApi.chapters.get.mockResolvedValue({
      type: 'chapter',
      attrs: { id: 'ch-1', title: 'Introduction' },
      content: [],
    })

    render(<ChapterView document={mockDocument} onBack={onBack} />)
    await user.click(await screen.findByRole('button', { name: 'New Chapter' }))

    await user.type(screen.getByLabelText('Chapter Title'), 'Introduction')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Introduction' })).toBeInTheDocument()
    })
  })

  it('hides the form after successful creation', async () => {
    const user = userEvent.setup()
    mockedApi.chapters.create.mockResolvedValue({
      status: { code: 'ok', message: 'created' },
    })

    render(<ChapterView document={mockDocument} onBack={onBack} />)
    await user.click(await screen.findByRole('button', { name: 'New Chapter' }))

    await user.type(screen.getByLabelText('Chapter Title'), 'Introduction')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.queryByLabelText('Chapter Title')).not.toBeInTheDocument()
    })
  })

  it('shows error when creation fails', async () => {
    const user = userEvent.setup()
    mockedApi.chapters.create.mockRejectedValue(new Error('Server error'))

    render(<ChapterView document={mockDocument} onBack={onBack} />)
    await user.click(await screen.findByRole('button', { name: 'New Chapter' }))

    await user.type(screen.getByLabelText('Chapter Title'), 'Introduction')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })
  })

  it('hides form when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<ChapterView document={mockDocument} onBack={onBack} />)

    await user.click(await screen.findByRole('button', { name: 'New Chapter' }))
    expect(screen.getByLabelText('Chapter Title')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Chapter Title')).not.toBeInTheDocument()
  })
})
