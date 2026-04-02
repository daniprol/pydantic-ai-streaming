import { screen } from '@testing-library/react'

import { FlowNav } from '@/features/navigation/components/FlowNav'
import { renderWithProviders } from '@/test/utils'

describe('FlowNav', () => {
  it('renders all four sections and highlights the active flow', () => {
    renderWithProviders(<FlowNav activeFlow="temporal" />)

    expect(screen.getByRole('link', { name: 'Basic' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'DBOS' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Temporal' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Replay' })).toBeInTheDocument()
    expect(screen.getByText('Multi-flow PydanticAI playground')).toBeInTheDocument()
  })
})
