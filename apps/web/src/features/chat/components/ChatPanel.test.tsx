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
                  properties: {},
                },
                fields: [
                  {
                    kind: 'email',
                    label: 'Email',
                    name: 'email',
                    required: true,
                  },
                ],
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
                  properties: {},
                },
                fields: [
                  {
                    kind: 'email',
                    label: 'Email',
                    name: 'email',
                    required: true,
                  },
                ],
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
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })

  it('renders resolved form data after submission', () => {
    chatState.messages = [
      {
        id: 'assistant-resolved-form',
        role: 'assistant',
        parts: [
          {
            input: { title: 'Form required' },
            output: { email: 'name@example.com', notes: 'Customer confirmed' },
            state: 'output-available',
            toolCallId: 'tool-form',
            type: 'tool-collect_human_form',
          },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-resolved-form"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-resolved-form',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-form',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-form',
              request_metadata_json: {},
              resolution_json: { result: { email: 'name@example.com', notes: 'Customer confirmed' } },
              resolved_at: '2026-04-06T00:01:00Z',
              status: 'resolved',
              tool_call_id: 'tool-form',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                description: 'Please confirm the customer onboarding details.',
                fields: [
                  { kind: 'email', label: 'Email', name: 'email', required: true },
                  { kind: 'textarea', label: 'Notes', name: 'notes', required: false },
                ],
                title: 'Form required',
              },
            },
          ],
        }}
      />,
    )

    expect(screen.getByText('Submitted')).toBeInTheDocument()
    expect(screen.getByText(/name@example.com/)).toBeInTheDocument()
    expect(screen.getByText('Email')).toBeInTheDocument()
    expect(screen.getByText('Please confirm the customer onboarding details.')).toBeInTheDocument()
    expect(screen.queryByText(/Tool call:/)).not.toBeInTheDocument()
  })

  it('allows cancelling a pending form and resumes via tool output', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-cancel-form',
        role: 'assistant',
        parts: [
          { type: 'tool-collect_human_form', state: 'input-available', toolCallId: 'tool-cancel-form' },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-cancel-form"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-cancel-form',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-cancel-form',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-cancel-form',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-cancel-form',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                cancelLabel: 'Cancel',
                fields: [
                  { kind: 'email', label: 'Email', name: 'email', required: true },
                ],
                schema: { properties: {} },
                submitLabel: 'Send form',
                title: 'Form required',
              },
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(chatState.addToolOutput).toHaveBeenCalledWith({
      output: {
        status: 'cancelled',
      },
      tool: 'collect_human_form',
      toolCallId: 'tool-cancel-form',
    })
  })

  it('resumes immediately after cancelling a form before allowing the next user message', async () => {
    const user = userEvent.setup()
    chatState.messages = [
      {
        id: 'assistant-cancel-followup',
        role: 'assistant',
        parts: [{ type: 'tool-collect_human_form', state: 'input-available', toolCallId: 'tool-cancel-followup' }],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-cancel-followup"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-cancel-followup',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-cancel-followup',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-cancel-followup',
              request_metadata_json: {},
              resolution_json: null,
              resolved_at: null,
              status: 'pending',
              tool_call_id: 'tool-cancel-followup',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                cancelLabel: 'Cancel',
                fields: [{ kind: 'email', label: 'Email', name: 'email', required: true }],
                submitLabel: 'Send form',
                title: 'Quick info form',
              },
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(chatState.sendMessage).toHaveBeenCalledWith()

    chatState.sendMessage.mockClear()

    await user.type(screen.getByPlaceholderText('Ask about an order, service health, or support policy...'), 'what did i do?')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(chatState.sendMessage).toHaveBeenCalledWith({ text: 'what did i do?' })
  })

  it('renders cancelled forms as a compact summary', () => {
    chatState.messages = [
      {
        id: 'assistant-cancelled-form',
        role: 'assistant',
        parts: [
          {
            input: { title: 'Preferences form' },
            output: { status: 'cancelled' },
            state: 'output-available',
            toolCallId: 'tool-cancelled-form',
            type: 'tool-collect_human_form',
          },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-cancelled-form"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-cancelled-form',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-cancelled-form',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-cancelled-form',
              request_metadata_json: {},
              resolution_json: { result: { status: 'cancelled' } },
              resolved_at: '2026-04-06T00:01:00Z',
              status: 'cancelled',
              tool_call_id: 'tool-cancelled-form',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                description: 'Collect the minimum customer details before proceeding.',
                fields: [{ kind: 'email', label: 'Email', name: 'email', required: true }],
                title: 'Preferences form',
              },
            },
          ],
        }}
      />,
    )

    expect(screen.getByText('Cancelled')).toBeInTheDocument()
    expect(screen.getByText('Collect the minimum customer details before proceeding.')).toBeInTheDocument()
    expect(screen.getByText('The form was cancelled and the conversation can continue.')).toBeInTheDocument()
  })

  it('renders cancelled forms as cancelled summaries after reopening a conversation', () => {
    chatState.messages = [
      {
        id: 'assistant-reopened-cancelled-form',
        role: 'assistant',
        parts: [
          {
            input: { title: 'Quick info form' },
            output: { status: 'cancelled' },
            state: 'output-available',
            toolCallId: 'tool-reopened-cancelled-form',
            type: 'tool-collect_human_form',
          },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-reopened-cancelled-form"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-reopened-cancelled-form',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-reopened-cancelled-form',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-reopened-cancelled-form',
              request_metadata_json: {},
              resolution_json: { result: { status: 'cancelled' } },
              resolved_at: '2026-04-06T00:01:00Z',
              status: 'cancelled',
              tool_call_id: 'tool-reopened-cancelled-form',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                description: 'Please collect: name (optional), email (optional), and a brief description of your request.',
                fields: [{ kind: 'email', label: 'Email', name: 'email', required: false }],
                title: 'Quick info form',
              },
            },
          ],
        }}
      />,
    )

    expect(screen.getByText('Cancelled')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send preferences' })).not.toBeInTheDocument()
  })

  it('renders duplicate resolved HITL tool calls only once per tool call id', () => {
    chatState.messages = [
      {
        id: 'assistant-duplicate-cancelled-form',
        role: 'assistant',
        parts: [
          {
            input: { title: 'Preferences form' },
            output: { status: 'cancelled' },
            state: 'output-available',
            toolCallId: 'tool-duplicate-form',
            type: 'tool-collect_human_form',
          },
          {
            input: { title: 'Preferences form' },
            output: { status: 'cancelled' },
            state: 'output-available',
            toolCallId: 'tool-duplicate-form',
            type: 'tool-collect_human_form',
          },
        ],
      },
    ]

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-duplicate-cancelled-form"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-duplicate-cancelled-form',
          flow_type: 'basic',
          messages: chatState.messages,
          pending_tool_calls: [
            {
              approval_id: null,
              args_json: {},
              created_at: '2026-04-06T00:00:00Z',
              id: 'pending-duplicate-cancelled-form',
              kind: 'form',
              message_sequence: 1,
              pending_group_id: 'group-duplicate-cancelled-form',
              request_metadata_json: {},
              resolution_json: { result: { status: 'cancelled' } },
              resolved_at: '2026-04-06T00:01:00Z',
              status: 'cancelled',
              tool_call_id: 'tool-duplicate-form',
              tool_name: 'collect_human_form',
              ui_payload_json: {
                fields: [{ kind: 'email', label: 'Email', name: 'email', required: true }],
                title: 'Preferences form',
              },
            },
          ],
        }}
      />,
    )

    expect(screen.getAllByText('The form was cancelled and the conversation can continue.')).toHaveLength(1)
  })

  it('renders a friendly pending-tool conflict error message', () => {
    chatState.error = new Error(
      JSON.stringify({
        detail: {
          message: 'Resolve pending tool calls before sending another message.',
          pendingToolCallIds: ['tool-1', 'tool-2'],
        },
      }),
    )
    chatState.messages = []
    chatState.status = 'error'

    renderWithProviders(
      <ChatPanel
        conversationId="conversation-conflict"
        flow="basic"
        initialData={{
          active_replay_id: null,
          conversation_id: 'conversation-conflict',
          flow_type: 'basic',
          messages: [],
          pending_tool_calls: [],
        }}
      />,
    )

    expect(screen.getByText('Resolve pending tool calls before sending another message.')).toBeInTheDocument()
    expect(screen.queryByText(/tool-1/)).not.toBeInTheDocument()
  })
})
