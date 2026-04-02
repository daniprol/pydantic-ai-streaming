import type {
  ConversationListResponse,
  ConversationMessagesResponse,
  FlowType,
} from '@/types/chat'

const API_BASE = '/api/v1'

async function apiFetch<T>(path: string, sessionId: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Session-Id': sessionId,
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  return (await response.json()) as T
}

export function fetchConversations(flow: FlowType, sessionId: string) {
  return apiFetch<ConversationListResponse>(
    `/flows/${flow}/conversations?page=1&page_size=50&sort=updated_at&direction=desc`,
    sessionId,
  )
}

export function fetchConversationMessages(
  flow: FlowType,
  conversationId: string,
  sessionId: string,
) {
  return apiFetch<ConversationMessagesResponse>(
    `/flows/${flow}/conversations/${conversationId}/messages`,
    sessionId,
  )
}
