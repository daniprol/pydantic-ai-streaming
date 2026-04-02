import { screen } from '@testing-library/react'

import { ConversationSidebar } from '@/features/conversations/components/ConversationSidebar'
import { renderWithProviders } from '@/test/utils'

describe('ConversationSidebar', () => {
  it('renders conversation links for the active flow', () => {
    renderWithProviders(
      <ConversationSidebar
        flow="dbos"
        currentConversationId="conversation-1"
        conversations={[
          {
            id: 'conversation-1',
            flow_type: 'dbos',
            title: 'Order help',
            preview: 'Check order 123',
            active_replay_id: null,
            created_at: '2026-04-02T10:00:00Z',
            updated_at: '2026-04-02T10:05:00Z',
          },
        ]}
      />,
    )

    expect(screen.getByRole('link', { name: /Order help/i })).toHaveAttribute(
      'href',
      '/dbos/conversations/conversation-1',
    )
    expect(screen.getByRole('link', { name: /New chat/i })).toHaveAttribute('href', '/dbos')
  })
})
