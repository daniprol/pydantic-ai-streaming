import type { UIMessage } from 'ai'
import { describe, expect, it } from 'vitest'

import { lastAssistantMessageIsCompleteWithHitlResponses } from '@/features/chat/lib/autoSubmit'

function asUiMessage(message: unknown): UIMessage {
  return message as UIMessage
}

describe('lastAssistantMessageIsCompleteWithHitlResponses', () => {
  it('returns true after an approval response is recorded', () => {
    expect(
      lastAssistantMessageIsCompleteWithHitlResponses({
        messages: [
          asUiMessage({
            id: 'assistant-1',
            role: 'assistant',
            parts: [
              {
                approval: { approved: true, id: 'approval-1' },
                state: 'approval-responded',
                toolCallId: 'tool-1',
                type: 'tool-request_human_approval',
              },
            ],
          }),
        ],
      }),
    ).toBe(true)
  })

  it('returns true after a deferred tool output is provided', () => {
    expect(
      lastAssistantMessageIsCompleteWithHitlResponses({
        messages: [
          asUiMessage({
            id: 'assistant-2',
            role: 'assistant',
            parts: [
              {
                input: { title: 'Decision required' },
                output: { decision: 'accepted' },
                state: 'output-available',
                toolCallId: 'tool-2',
                type: 'tool-request_human_decision',
              },
            ],
          }),
        ],
      }),
    ).toBe(true)
  })

  it('returns true for mixed completed approvals and deferred tool outputs', () => {
    expect(
      lastAssistantMessageIsCompleteWithHitlResponses({
        messages: [
          asUiMessage({
            id: 'assistant-3',
            role: 'assistant',
            parts: [
              {
                approval: { approved: true, id: 'approval-2' },
                state: 'approval-responded',
                toolCallId: 'tool-3',
                type: 'tool-request_human_approval',
              },
              {
                input: { title: 'Form required' },
                output: { email: 'name@example.com' },
                state: 'output-available',
                toolCallId: 'tool-4',
                type: 'tool-collect_human_form',
              },
            ],
          }),
        ],
      }),
    ).toBe(true)
  })

  it('returns false when approval is still pending', () => {
    expect(
      lastAssistantMessageIsCompleteWithHitlResponses({
        messages: [
          asUiMessage({
            id: 'assistant-4',
            role: 'assistant',
            parts: [
              {
                approval: { id: 'approval-3' },
                state: 'approval-requested',
                toolCallId: 'tool-5',
                type: 'tool-request_human_approval',
              },
            ],
          }),
        ],
      }),
    ).toBe(false)
  })

  it('returns false when a deferred tool call still needs input', () => {
    expect(
      lastAssistantMessageIsCompleteWithHitlResponses({
        messages: [
          asUiMessage({
            id: 'assistant-5',
            role: 'assistant',
            parts: [
              {
                input: { title: 'Decision required' },
                state: 'input-available',
                toolCallId: 'tool-6',
                type: 'tool-request_human_decision',
              },
            ],
          }),
        ],
      }),
    ).toBe(false)
  })
})
