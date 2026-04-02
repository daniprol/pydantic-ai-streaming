import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { FlowChatPage } from '@/app/pages/FlowChatPage'
import { NotFoundPage } from '@/app/pages/NotFoundPage'
import { ApiError } from '@/features/chat/api/client'
import { renderWithProviders } from '@/test/utils'

const conversationMessagesState = vi.hoisted(() => ({
  data: undefined,
  isError: false,
  error: undefined as ApiError | undefined,
}))

vi.mock('@/stores/ui-store', () => ({
  useUIStore: (selector: (state: { sessionId: string }) => string) => selector({ sessionId: 'session-1' }),
}))

vi.mock('@/features/conversations/hooks/useConversations', () => ({
  useConversations: () => ({
    data: {
      items: [],
    },
  }),
  useConversationMessages: () => conversationMessagesState,
}))

vi.mock('@/features/chat/components/ChatPanel', () => ({
  ChatPanel: () => <div>Chat panel</div>,
}))

describe('FlowChatPage', () => {
  it('renders the shared layout for a valid flow route', () => {
    conversationMessagesState.data = undefined
    conversationMessagesState.isError = false
    conversationMessagesState.error = undefined

    renderWithProviders(
      <Routes>
        <Route path="/:flow" element={<FlowChatPage />} />
      </Routes>,
      ['/basic'],
    )

    expect(screen.getByText('Direct PydanticAI streaming')).toBeInTheDocument()
    expect(screen.getByText('Chat panel')).toBeInTheDocument()
    expect(screen.getByText('Current flow history')).toBeInTheDocument()
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
