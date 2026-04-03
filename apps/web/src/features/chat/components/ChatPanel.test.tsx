import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ChatPanel } from '@/features/chat/components/ChatPanel'
import type { UIConversationMessage } from '@/types/chat'
import { renderWithProviders } from '@/test/utils'

const chatState = vi.hoisted(() => ({
  error: undefined as Error | undefined,
  messages: [] as UIConversationMessage[],
  regenerate: vi.fn().mockResolvedValue(undefined),
  sendMessage: vi.fn().mockResolvedValue(undefined),
  status: 'ready',
  stop: vi.fn(),
}))

vi.mock('@ai-sdk/react', () => ({
  useChat: () => chatState,
}))

describe('ChatPanel', () => {
  it('renders a clean composer with the shared ai-elements placeholder', () => {
    chatState.messages = []
    chatState.status = 'ready'
    chatState.error = undefined

    renderWithProviders(<ChatPanel flow="basic" />)

    expect(screen.getByText('Start a conversation')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Ask about an order, service health, or support policy...')).toBeInTheDocument()
  })

  it('groups three consecutive tool calls into a compact queue', () => {
    chatState.messages = [
      {
        id: 'assistant-1',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'Let me check that for you.' },
          { type: 'tool-lookup_order_status', state: 'output-available', toolCallId: 'tool-1' },
          { type: 'tool-check_service_health', state: 'input-available', toolCallId: 'tool-2' },
          { type: 'tool-search_help_center', state: 'output-available', toolCallId: 'tool-3' },
          { type: 'text', text: 'Here is the latest update.' },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-1"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-1',
          flow_type: 'basic',
          messages: chatState.messages,
        }}
      />,
    )

    expect(screen.getByRole('button', { name: /3 background steps/i })).toBeInTheDocument()
    expect(screen.getByText('Let me check that for you.')).toBeInTheDocument()
    expect(screen.getByText('Here is the latest update.')).toBeInTheDocument()
  })

  it('renders persisted tool events without crashing when the tool name is missing', () => {
    chatState.messages = [
      {
        id: 'assistant-2',
        role: 'assistant',
        parts: [
          { type: 'tool-result', toolCallId: 'tool-4' },
          { type: 'text', text: 'Done.' },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-2"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-2',
          flow_type: 'basic',
          messages: chatState.messages,
        }}
      />,
    )

    expect(screen.getByText('Background step')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
  })
})
