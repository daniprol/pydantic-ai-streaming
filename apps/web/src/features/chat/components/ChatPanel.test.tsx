import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from '@/features/chat/components/ChatPanel'
import type { UIConversationMessage } from '@/types/chat'
import { renderWithProviders } from '@/test/utils'

const chatState = vi.hoisted(() => ({
  addToolApprovalResponse: vi.fn().mockResolvedValue(undefined),
  addToolOutput: vi.fn().mockResolvedValue(undefined),
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
  beforeEach(() => {
    chatState.addToolApprovalResponse.mockClear()
    chatState.addToolOutput.mockClear()
    chatState.regenerate.mockClear()
    chatState.sendMessage.mockClear()
    chatState.stop.mockClear()
    chatState.error = undefined
    chatState.messages = []
    chatState.status = 'ready'
  })

  it('submits approval rejection responses through the native AI SDK helper', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-reject-approval',
        role: 'assistant',
        parts: [
          {
            approval: { id: 'approval-reject' },
            input: { summary: 'Refund order-456' },
            state: 'approval-requested',
            toolCallId: 'tool-reject-approval',
            type: 'tool-request_human_approval',
          },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-reject-approval"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-reject-approval',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: 'approval-reject',
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-reject-approval',
              kind: 'approval',
              message_sequence: 1,
              pending_group_id: 'group-reject-approval',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-reject-approval',
              tool_name: 'request_human_approval',
              ui_payload_json: {
                confirmLabel: 'Approve',
                description: 'Review this action before it runs.',
                rejectLabel: 'Reject',
              },
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Reject' }))

    expect(chatState.addToolApprovalResponse).toHaveBeenCalledWith({
      approved: false,
      id: 'approval-reject',
    })
  })

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
          pending_tool_calls: [],
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
          pending_tool_calls: [],
        }}
      />,
    )

    expect(screen.getByText('Background step')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
  })

  it('submits a pending decision without sending a new user message', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-3',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'Please choose.' },
          { type: 'tool-request_human_decision', state: 'input-available', toolCallId: 'tool-1' },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-3"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-3',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-1',
              kind: 'decision',
              message_sequence: 1,
              pending_group_id: 'group-1',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-1',
              tool_name: 'request_human_decision',
              ui_payload_json: {
                acceptLabel: 'Accept',
                description: 'Need a choice',
                rejectLabel: 'Reject',
                title: 'Decision required',
              },
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Accept' }))

    expect(chatState.addToolOutput).toHaveBeenCalledWith({
      output: {
        decision: 'accepted',
      },
      tool: 'request_human_decision',
      toolCallId: 'tool-1',
    })
  })

  it('submits a rejected pending decision without sending a new user message', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-reject-decision',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'Please choose.' },
          { type: 'tool-request_human_decision', state: 'input-available', toolCallId: 'tool-reject-decision' },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-reject-decision"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-reject-decision',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-reject-decision',
              kind: 'decision',
              message_sequence: 1,
              pending_group_id: 'group-reject-decision',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-reject-decision',
              tool_name: 'request_human_decision',
              ui_payload_json: {
                acceptLabel: 'Accept',
                description: 'Need a choice',
                rejectLabel: 'Reject',
                title: 'Decision required',
              },
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Reject' }))

    expect(chatState.addToolOutput).toHaveBeenCalledWith({
      output: {
        decision: 'rejected',
      },
      tool: 'request_human_decision',
      toolCallId: 'tool-reject-decision',
    })
  })

  it('renders and submits a pending form', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-4',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'Please complete the form.' },
          { type: 'tool-collect_human_form', state: 'input-available', toolCallId: 'tool-2' },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-4"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-4',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-2',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-2',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-2',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                schema: {
                  fields: [
                    {
                      kind: 'text',
                      label: 'Email',
                      name: 'email',
                      required: true,
                    },
                  ],
                },
                submitLabel: 'Send form',
                title: 'Form required',
              },
            },
          ],
        }}
      />,
    )

    await user.type(screen.getByLabelText('Email'), 'name@example.com')
    await user.click(screen.getByRole('button', { name: 'Send form' }))

    expect(chatState.addToolOutput).toHaveBeenCalledWith({
      output: {
        email: 'name@example.com',
      },
      tool: 'collect_human_form',
      toolCallId: 'tool-2',
    })
  })

  it('does not submit a pending form when a required field is missing', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-form-validation',
        role: 'assistant',
        parts: [
          { type: 'text', text: 'Please complete the form.' },
          { type: 'tool-collect_human_form', state: 'input-available', toolCallId: 'tool-form-validation' },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-form-validation"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-form-validation',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-form-validation',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-form-validation',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-form-validation',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                schema: {
                  fields: [
                    {
                      kind: 'text',
                      label: 'Email',
                      name: 'email',
                      required: true,
                    },
                  ],
                },
                submitLabel: 'Send form',
                title: 'Form required',
              },
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Send form' }))

    expect(chatState.addToolOutput).not.toHaveBeenCalled()
    expect(screen.getByText('Email is required')).toBeInTheDocument()
  })

  it('submits approval responses through the native AI SDK helper', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-5',
        role: 'assistant',
        parts: [
          {
            approval: { id: 'approval-1' },
            input: { summary: 'Refund order-123' },
            state: 'approval-requested',
            toolCallId: 'tool-3',
            type: 'tool-request_human_approval',
          },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-5"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-5',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: 'approval-1',
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-3',
              kind: 'approval',
              message_sequence: 1,
              pending_group_id: 'group-3',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-3',
              tool_name: 'request_human_approval',
              ui_payload_json: {
                confirmLabel: 'Approve',
                description: 'Review this action before it runs.',
                rejectLabel: 'Reject',
              },
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Approve' }))

    expect(chatState.addToolApprovalResponse).toHaveBeenCalledWith({
      approved: true,
      id: 'approval-1',
    })
  })

  it('does not render actionable HITL controls for resolved pending calls after reload', () => {
    chatState.messages = [
      {
        id: 'assistant-resolved-approval',
        role: 'assistant',
        parts: [
          {
            approval: { id: 'approval-1', approved: true },
            input: { summary: 'Refund order-123' },
            state: 'approval-responded',
            toolCallId: 'tool-3',
            type: 'tool-request_human_approval',
          },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-resolved"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-resolved',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: 'approval-1',
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-resolved',
              kind: 'approval',
              message_sequence: 1,
              pending_group_id: 'group-resolved',
              request_metadata_json: {},
              resolution_json: { approved: true },
              resolved_at: '2026-04-06T00:01:00Z',
              status: 'resolved',
              tool_call_id: 'tool-3',
              tool_name: 'request_human_approval',
              ui_payload_json: {
                confirmLabel: 'Approve',
                description: 'Review this action before it runs.',
                rejectLabel: 'Reject',
              },
            },
          ],
        }}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
  })
})
