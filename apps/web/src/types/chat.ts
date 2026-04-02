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

export interface ConversationListResponse {
  items: ConversationSummary[]
  page: number
  page_size: number
  total: number
}

export interface ConversationMessagesResponse {
  conversation_id: string
  flow_type: FlowType
  active_replay_id: string | null
  messages: UIConversationMessage[]
}

export interface UIConversationMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  parts: Array<Record<string, unknown>>
  metadata?: unknown
}
