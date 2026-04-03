import type {
  ConversationCreateResponse,
  ConversationListResponse,
  ConversationMessagesResponse,
  FlowType,
} from '@/types/chat'

import { apiUrl } from '@/features/chat/api/base'

export class ApiError extends Error {
  status: number

  constructor(status: number, message?: string) {
    super(message ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json')

  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
  })

  if (!response.ok) {
    throw new ApiError(response.status)
  }

  return (await response.json()) as T
}

export function fetchConversations(flow: FlowType) {
  return apiFetch<ConversationListResponse>(`/flows/${flow}/conversations`)
}

export function createConversation(flow: FlowType) {
  return apiFetch<ConversationCreateResponse>(`/flows/${flow}/conversations`, {
    method: 'POST',
  })
}

export function deleteConversation(flow: FlowType, conversationId: string) {
  return apiFetch<null>(`/flows/${flow}/conversations/${conversationId}`, { method: 'DELETE' }).then(() => undefined)
}

export function fetchConversationMessages(flow: FlowType, conversationId: string) {
  return apiFetch<ConversationMessagesResponse>(`/flows/${flow}/conversations/${conversationId}/messages`)
}
