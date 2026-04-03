import { createTransport } from '@/features/chat/lib/transports'

describe('createTransport', () => {
  it('sends only the latest message while preserving extra request body fields', () => {
    const transport = createTransport({
      flow: 'basic',
      conversationId: 'conversation-1',
      replayId: null,
    }) as unknown as {
      prepareSendMessagesRequest: (input: {
        messages: { id: string }[]
        body?: Record<string, unknown>
        id?: string
      }) => { body: Record<string, unknown> }
    }

    const request = transport.prepareSendMessagesRequest({
      id: 'request-1',
      body: { deferredToolResults: { approvals: { a: true } } },
      messages: [{ id: 'one' }, { id: 'two' }],
    })

    expect(request.body.trigger).toBe('submit-message')
    expect(request.body.id).toBe('request-1')
    expect(request.body.messages).toEqual([{ id: 'two' }])
    expect(request.body.deferredToolResults).toEqual({ approvals: { a: true } })
  })
})
