import { useQuery } from '@tanstack/react-query'

import { fetchConversationMessages, fetchConversations } from '@/features/chat/api/client'
import type { FlowType } from '@/types/chat'

export function useConversations(flow: FlowType, sessionId: string) {
  return useQuery({
    queryKey: ['conversations', flow, sessionId],
    queryFn: () => fetchConversations(flow, sessionId),
  })
}

export function useConversationMessages(
  flow: FlowType,
  conversationId: string | undefined,
  sessionId: string,
) {
  return useQuery({
    queryKey: ['conversation-messages', flow, conversationId, sessionId],
    queryFn: () => fetchConversationMessages(flow, conversationId!, sessionId),
    enabled: Boolean(conversationId),
  })
}
