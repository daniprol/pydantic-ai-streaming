import { screen } from '@testing-library/react'

import { Part } from '@/Part'
import { renderWithProviders } from '@/test/utils'

describe('Part', () => {
  it('renders a reasoning block', () => {
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

    expect(screen.getByText('Thinking through the answer')).toBeInTheDocument()
  })
})
