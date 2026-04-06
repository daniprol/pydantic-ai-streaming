export type FlowType = 'basic' | 'dbos' | 'temporal' | 'dbos-replay'

export interface ConversationSummary {
  id: string
  flow_type: FlowType
  title: string | null
  preview: string | null
  active_replay_id: string | null
  created_at: string
  updated_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  skip: number
  limit: number
  total: number
}

export interface ConversationListResponse extends PaginatedResponse<ConversationSummary> {
  items: ConversationSummary[]
}

export interface ConversationCreateResponse {
  conversation: ConversationSummary
}

export interface ConversationMessagesResponse {
  conversation_id: string
  flow_type: FlowType
  active_replay_id: string | null
  messages: UIConversationMessage[]
  pending_tool_calls: PendingToolCall[]
}

export type PendingToolCallKind = 'approval' | 'decision' | 'form'
export type PendingToolCallStatus = 'pending' | 'resolved' | 'denied' | 'cancelled'

export interface PendingToolCall {
  id: string
  tool_call_id: string
  pending_group_id: string
  tool_name: string
  kind: PendingToolCallKind
  status: PendingToolCallStatus
  message_sequence: number
  approval_id: string | null
  args_json: Record<string, unknown>
  request_metadata_json: Record<string, unknown>
  ui_payload_json: Record<string, unknown>
  resolution_json: Record<string, unknown> | null
  created_at: string
  resolved_at: string | null
}

export interface HitlRequestData {
  toolCallId: string
  toolName: string
  kind: PendingToolCallKind
  status: PendingToolCallStatus
  payload: Record<string, unknown>
}

export interface ChatDataParts {
  hitl_request: HitlRequestData
}

export interface UIConversationMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  parts: Record<string, unknown>[]
  metadata?: unknown
}
