import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { FlowChatPage } from '@/app/pages/FlowChatPage'
import { NotFoundPage } from '@/app/pages/NotFoundPage'
import { ApiError } from '@/features/chat/api/client'
import type { ConversationMessagesResponse } from '@/types/chat'
import { renderWithProviders } from '@/test/utils'

const conversationMessagesState = vi.hoisted(() => ({
  data: undefined as ConversationMessagesResponse | undefined,
  error: undefined as ApiError | undefined,
  isError: false,
}))

vi.mock('@/features/conversations/hooks/useConversations', () => ({
  useConversations: () => ({
    data: {
      items: [],
    },
    isLoading: false,
  }),
  useConversationMessages: () => conversationMessagesState,
  useDeleteConversation: () => ({
    mutateAsync: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/features/chat/components/ChatPanel', () => ({
  ChatPanel: () => <div>Chat panel</div>,
}))

describe('FlowChatPage', () => {
  it('renders the shared layout for a draft conversation route', () => {
    conversationMessagesState.data = undefined
    conversationMessagesState.isError = false
    conversationMessagesState.error = undefined

    renderWithProviders(
      <Routes>
        <Route path="/:flow" element={<FlowChatPage />} />
      </Routes>,
      ['/basic'],
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Basic' })).toBeInTheDocument()
    expect(screen.getByText('Chat panel')).toBeInTheDocument()
  })

  it('shows a loading state while a saved conversation is being fetched', () => {
    conversationMessagesState.data = undefined
    conversationMessagesState.isError = false
    conversationMessagesState.error = undefined

    renderWithProviders(
      <Routes>
        <Route path="/:flow/conversations/:conversationId" element={<FlowChatPage />} />
      </Routes>,
      ['/basic/conversations/conversation-1'],
    )

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('Chat panel')).not.toBeInTheDocument()
  })

  it('renders the chat panel after a saved conversation loads', () => {
    conversationMessagesState.data = {
      active_replay_id: null,
      conversation_id: 'conversation-1',
      flow_type: 'basic',
      messages: [],
    }
    conversationMessagesState.isError = false
    conversationMessagesState.error = undefined

    renderWithProviders(
      <Routes>
        <Route path="/:flow/conversations/:conversationId" element={<FlowChatPage />} />
      </Routes>,
      ['/basic/conversations/conversation-1'],
    )

    expect(screen.getByText('Chat panel')).toBeInTheDocument()
  })

  it('shows a not-found state for missing persisted conversations', () => {
    conversationMessagesState.data = undefined
    conversationMessagesState.isError = true
    conversationMessagesState.error = new ApiError(404)

    renderWithProviders(
      <Routes>
        <Route path="/:flow/conversations/:conversationId" element={<FlowChatPage />} />
        <Route path="/not-found" element={<NotFoundPage />} />
      </Routes>,
      ['/basic/conversations/missing'],
    )

    expect(screen.getByText('Conversation not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start a new conversation' })).toHaveAttribute('href', '/basic')
  })
})
