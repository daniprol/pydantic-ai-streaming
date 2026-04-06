import { createTransport } from '@/features/chat/lib/transports'

describe('createTransport', () => {
  it('sends only the latest message while preserving extra request body fields', () => {
    const transport = createTransport({
      flow: 'basic',
      conversationId: 'conversation-1',
      replayId: null,
    }) as unknown as {
      prepareSendMessagesRequest: (input: {
        messages: { id: string; parts?: unknown[]; role?: string }[]
        body?: Record<string, unknown>
        id?: string
      }) => { body: Record<string, unknown> }
    }

    const request = transport.prepareSendMessagesRequest({
      id: 'request-1',
      body: { custom: true },
      messages: [
        { id: 'one', role: 'assistant' },
        { id: 'two', role: 'user' },
      ],
    })

    expect(request.body.trigger).toBe('submit-message')
    expect(request.body.id).toBe('request-1')
    expect(request.body.messages).toEqual([{ id: 'two', role: 'user' }])
    expect(request.body.custom).toBe(true)
  })

  it('sends assistant tool-part updates when resuming a deferred tool call', () => {
    const transport = createTransport({
      flow: 'basic',
      conversationId: 'conversation-1',
      replayId: null,
    }) as unknown as {
      prepareSendMessagesRequest: (input: {
        messages: Array<{ id: string; parts?: unknown[]; role?: string }>
        body?: Record<string, unknown>
        id?: string
      }) => { body: Record<string, unknown> }
    }

    const request = transport.prepareSendMessagesRequest({
      id: 'request-2',
      body: {},
      messages: [
        {
          id: 'one',
          parts: [
            {
              output: { decision: 'accepted' },
              state: 'output-available',
              toolCallId: 'tool-1',
              type: 'tool-request_human_decision',
            },
          ],
          role: 'assistant',
        },
      ],
    })

    expect(request.body.messages).toEqual([
      {
        id: 'one',
        parts: [
          {
            output: { decision: 'accepted' },
            state: 'output-available',
            toolCallId: 'tool-1',
            type: 'tool-request_human_decision',
          },
        ],
        role: 'assistant',
      },
    ])
  })

  it('sends assistant approval responses when resuming an approval request', () => {
    const transport = createTransport({
      flow: 'basic',
      conversationId: 'conversation-1',
      replayId: null,
    }) as unknown as {
      prepareSendMessagesRequest: (input: {
        messages: Array<{ id: string; parts?: unknown[]; role?: string }>
        body?: Record<string, unknown>
        id?: string
      }) => { body: Record<string, unknown> }
    }

    const request = transport.prepareSendMessagesRequest({
      id: 'request-3',
      body: {},
      messages: [
        {
          id: 'assistant-approval',
          parts: [
            {
              approval: { approved: true, id: 'approval-1' },
              state: 'approval-responded',
              toolCallId: 'tool-2',
              type: 'tool-request_human_approval',
            },
          ],
          role: 'assistant',
        },
      ],
    })

    expect(request.body.messages).toEqual([
      {
        id: 'assistant-approval',
        parts: [
          {
            approval: { approved: true, id: 'approval-1' },
            state: 'approval-responded',
            toolCallId: 'tool-2',
            type: 'tool-request_human_approval',
          },
        ],
        role: 'assistant',
      },
    ])
  })
})
