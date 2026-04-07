import { createTransport } from '@/features/chat/lib/transports'

describe('createTransport', () => {
  it('sends the latest user message and preceding assistant context when present', () => {
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

  it('does not resend assistant HITL parts when sending a normal follow-up user message', () => {
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
      id: 'request-mixed-hitl',
      body: {},
      messages: [
        {
          id: 'assistant-hitl',
          parts: [
            {
              output: { status: 'cancelled' },
              state: 'output-available',
              toolCallId: 'tool-form',
              type: 'tool-collect_human_form',
            },
          ],
          role: 'assistant',
        },
        { id: 'user-next', role: 'user' },
      ],
    })

    expect(request.body.messages).toEqual([{ id: 'user-next', role: 'user' }])
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

  it('sends cancelled form outputs when resuming a deferred form call', () => {
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
      id: 'request-4',
      body: {},
      messages: [
        {
          id: 'assistant-form-cancel',
          parts: [
            {
              output: { status: 'cancelled' },
              state: 'output-available',
              toolCallId: 'tool-form',
              type: 'tool-collect_human_form',
            },
          ],
          role: 'assistant',
        },
      ],
    })

    expect(request.body.messages).toEqual([
      {
        id: 'assistant-form-cancel',
        parts: [
          {
            output: { status: 'cancelled' },
            state: 'output-available',
            toolCallId: 'tool-form',
            type: 'tool-collect_human_form',
          },
        ],
        role: 'assistant',
      },
    ])
  })

  it('does not resend hydrated deferred outputs when sending a follow-up message', () => {
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
      id: 'request-denied-followup',
      body: {},
      messages: [
        {
          id: 'assistant-form-denied',
          parts: [
            {
              output: { status: 'cancelled' },
              state: 'output-denied',
              toolCallId: 'tool-form-denied',
              type: 'tool-collect_human_form',
            },
          ],
          role: 'assistant',
        },
        { id: 'user-followup', role: 'user' },
      ],
    })

    expect(request.body.messages).toEqual([{ id: 'user-followup', role: 'user' }])
  })
})
