import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DocumentList } from '@/components/DocumentList'

vi.mock('@/api/client', () => ({
  api: {
    documents: {
      list: vi.fn(),
      create: vi.fn(),
      delete: vi.fn(),
    },
  },
}))

import { api } from '@/api/client'

const mockedApi = vi.mocked(api)

describe('DocumentList', () => {
  const onSelect = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.documents.list.mockResolvedValue([])
  })

  it('shows a "New Document" button', async () => {
    render(<DocumentList onSelect={onSelect} />)
    expect(await screen.findByText('New Document')).toBeInTheDocument()
  })

  it('shows a form with Title and Author inputs after clicking New Document', async () => {
    const user = userEvent.setup()
    render(<DocumentList onSelect={onSelect} />)

    await user.click(await screen.findByText('New Document'))

    expect(screen.getByLabelText('Title')).toBeInTheDocument()
    expect(screen.getByLabelText('Author')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument()
  })

  it('calls api.documents.create with correct payload on submit', async () => {
    const user = userEvent.setup()
    mockedApi.documents.create.mockResolvedValue({
      status: { code: 'ok', message: 'created' },
    })
    mockedApi.documents.list.mockResolvedValue([])

    render(<DocumentList onSelect={onSelect} />)
    await user.click(await screen.findByText('New Document'))

    await user.type(screen.getByLabelText('Title'), 'Faith')
    await user.type(screen.getByLabelText('Author'), 'Paul')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(mockedApi.documents.create).toHaveBeenCalledOnce()
    })

    const callArgs = mockedApi.documents.create.mock.calls[0][0]
    expect(callArgs.attrs.title).toBe('Faith')
    expect(callArgs.attrs.author).toBe('Paul')
    expect(callArgs.attrs.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    )
  })

  it('refreshes the document list after successful creation', async () => {
    const user = userEvent.setup()
    mockedApi.documents.create.mockResolvedValue({
      status: { code: 'ok', message: 'created' },
    })
    const existingDocs = [
      {
        attrs: { id: 'd-1', title: 'Existing', author: 'Someone' },
        chapter_summaries: [],
      },
    ]
    mockedApi.documents.list
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(existingDocs)

    render(<DocumentList onSelect={onSelect} />)
    await user.click(await screen.findByText('New Document'))
    await user.type(screen.getByLabelText('Title'), 'Faith')
    await user.type(screen.getByLabelText('Author'), 'Paul')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.getByText('Existing')).toBeInTheDocument()
    })
  })

  it('hides the form after successful creation', async () => {
    const user = userEvent.setup()
    mockedApi.documents.create.mockResolvedValue({
      status: { code: 'ok', message: 'created' },
    })

    render(<DocumentList onSelect={onSelect} />)
    await user.click(await screen.findByText('New Document'))
    await user.type(screen.getByLabelText('Title'), 'Faith')
    await user.type(screen.getByLabelText('Author'), 'Paul')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    })
  })

  it('shows error when creation fails', async () => {
    const user = userEvent.setup()
    mockedApi.documents.create.mockRejectedValue(new Error('Server error'))

    render(<DocumentList onSelect={onSelect} />)
    await user.click(await screen.findByText('New Document'))
    await user.type(screen.getByLabelText('Title'), 'Faith')
    await user.type(screen.getByLabelText('Author'), 'Paul')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })
  })

  it('hides form when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<DocumentList onSelect={onSelect} />)

    await user.click(await screen.findByText('New Document'))
    expect(screen.getByLabelText('Title')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
  })

  it('shows a Delete button next to each document', async () => {
    mockedApi.documents.list.mockResolvedValue([
      {
        attrs: { id: 'd-1', title: 'Faith', author: 'Paul' },
        chapter_summaries: [],
      },
    ])

    render(<DocumentList onSelect={onSelect} />)

    expect(
      await screen.findByRole('button', { name: 'Delete' })
    ).toBeInTheDocument()
  })

  it('calls api.documents.delete with the correct id', async () => {
    const user = userEvent.setup()
    mockedApi.documents.list.mockResolvedValue([
      {
        attrs: { id: 'd-1', title: 'Faith', author: 'Paul' },
        chapter_summaries: [],
      },
    ])
    mockedApi.documents.delete.mockResolvedValue({
      status: { code: 'ok', message: 'deleted' },
    })

    render(<DocumentList onSelect={onSelect} />)
    await screen.findByText('Faith')

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(mockedApi.documents.delete).toHaveBeenCalledWith('d-1')
    })
  })

  it('refreshes the list after successful deletion', async () => {
    const user = userEvent.setup()
    const docs = [
      {
        attrs: { id: 'd-1', title: 'Faith', author: 'Paul' },
        chapter_summaries: [],
      },
    ]
    mockedApi.documents.list
      .mockResolvedValueOnce(docs)
      .mockResolvedValueOnce([])
    mockedApi.documents.delete.mockResolvedValue({
      status: { code: 'ok', message: 'deleted' },
    })

    render(<DocumentList onSelect={onSelect} />)
    await screen.findByText('Faith')

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(screen.queryByText('Faith')).not.toBeInTheDocument()
    })
  })

  it('shows error when deletion fails', async () => {
    const user = userEvent.setup()
    mockedApi.documents.list.mockResolvedValue([
      {
        attrs: { id: 'd-1', title: 'Faith', author: 'Paul' },
        chapter_summaries: [],
      },
    ])
    mockedApi.documents.delete.mockRejectedValue(new Error('Delete failed'))

    render(<DocumentList onSelect={onSelect} />)
    await screen.findByText('Faith')

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(screen.getByText('Delete failed')).toBeInTheDocument()
    })
  })
})
