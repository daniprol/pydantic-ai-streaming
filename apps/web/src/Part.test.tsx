import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Part } from '@/Part'
import { renderWithProviders } from '@/test/utils'

describe('Part', () => {
  it('renders a reasoning block', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <Part
        part={{ type: 'reasoning', text: 'Thinking through the answer', state: 'done' } as never}
        message={{ id: 'assistant-1', role: 'assistant', parts: [] } as never}
        status="ready"
        regen={() => {}}
        index={0}
        lastMessage
      />,
    )

    await user.click(screen.getByRole('button', { name: /thought for a few seconds/i }))

    expect(screen.getByText('Thinking through the answer')).toBeInTheDocument()
  })
})
