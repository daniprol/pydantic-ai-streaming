import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ChatPanel } from '@/features/chat/components/ChatPanel'
import { renderWithProviders } from '@/test/utils'

const sendMessage = vi.fn()
const regenerate = vi.fn()

vi.mock('@ai-sdk/react', () => ({
  useChat: () => ({
    messages: [],
    sendMessage,
    status: 'ready',
    error: undefined,
    regenerate,
  }),
}))

describe('ChatPanel', () => {
  it('renders the shared composer copy for replay mode', () => {
    renderWithProviders(
      <ChatPanel
        flow="dbos-replay"
        conversationId="conversation-1"
        initialData={{
          conversation_id: 'conversation-1',
          flow_type: 'dbos-replay',
          active_replay_id: 'replay-1',
          messages: [],
        }}
      />,
    )

    expect(screen.getByText('Replay mode can reconnect to active streams.')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Ask about an order, service health, or support policy...')).toBeInTheDocument()
  })
})
