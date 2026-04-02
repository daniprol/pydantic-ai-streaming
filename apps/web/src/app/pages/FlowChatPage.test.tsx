import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

import { FlowChatPage } from '@/app/pages/FlowChatPage'
import { renderWithProviders } from '@/test/utils'

vi.mock('@/stores/ui-store', () => ({
  useUIStore: (selector: (state: { sessionId: string }) => string) => selector({ sessionId: 'session-1' }),
}))

vi.mock('@/features/conversations/hooks/useConversations', () => ({
  useConversations: () => ({
    data: {
      items: [],
    },
  }),
  useConversationMessages: () => ({
    data: undefined,
  }),
}))

vi.mock('@/features/chat/components/ChatPanel', () => ({
  ChatPanel: () => <div>Chat panel</div>,
}))

describe('FlowChatPage', () => {
  it('renders the shared layout for a valid flow route', () => {
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
})
