import type {
  ConversationCreateResponse,
  ConversationListResponse,
  ConversationMessagesResponse,
  FlowType,
} from '@/types/chat'

const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number

  constructor(status: number, message?: string) {
    super(message ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
  }
}

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
    throw new ApiError(response.status)
  }

  return (await response.json()) as T
}

export function fetchConversations(flow: FlowType, sessionId: string) {
  return apiFetch<ConversationListResponse>(`/flows/${flow}/conversations`, sessionId)
}

export function createConversation(flow: FlowType, sessionId: string) {
  return apiFetch<ConversationCreateResponse>(`/flows/${flow}/conversations`, sessionId, {
    method: 'POST',
  })
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
