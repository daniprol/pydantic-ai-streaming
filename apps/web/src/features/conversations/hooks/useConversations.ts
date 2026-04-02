import { useQuery } from '@tanstack/react-query'

import { ApiError, fetchConversationMessages, fetchConversations } from '@/features/chat/api/client'
import { chatQueryKeys } from '@/features/chat/api/queryKeys'
import type { FlowType } from '@/types/chat'

export function useConversations(flow: FlowType, sessionId: string) {
  return useQuery({
    queryKey: chatQueryKeys.conversations(flow, sessionId),
    queryFn: () => fetchConversations(flow, sessionId),
    staleTime: 30_000,
  })
}

export function useConversationMessages(
  flow: FlowType,
  conversationId: string | undefined,
  sessionId: string,
) {
  return useQuery({
    queryKey: conversationId
      ? chatQueryKeys.conversationMessages(flow, conversationId, sessionId)
      : ['conversation-messages', flow, 'draft', sessionId],
    queryFn: () => fetchConversationMessages(flow, conversationId!, sessionId),
    enabled: Boolean(conversationId),
    retry: (failureCount, error) => !(error instanceof ApiError && error.status === 404) && failureCount < 3,
    staleTime: 5_000,
  })
}
