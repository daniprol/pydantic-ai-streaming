import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, deleteConversation, fetchConversationMessages, fetchConversations } from '@/features/chat/api/client'
import { chatQueryKeys } from '@/features/chat/api/queryKeys'
import type { FlowType } from '@/types/chat'

export function useConversations(flow: FlowType) {
  return useQuery({
    queryKey: chatQueryKeys.conversations(flow),
    queryFn: () => fetchConversations(flow),
    staleTime: 30_000,
  })
}

export function useDeleteConversation(flow: FlowType) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (conversationId: string) => deleteConversation(flow, conversationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations(flow) })
    },
  })
}

export function useConversationMessages(flow: FlowType, conversationId: string | undefined) {
  return useQuery({
    queryKey: conversationId
      ? chatQueryKeys.conversationMessages(flow, conversationId)
      : ['conversation-messages', flow, 'draft'],
    queryFn: () => fetchConversationMessages(flow, conversationId!),
    enabled: Boolean(conversationId),
    retry: (failureCount, error) => !(error instanceof ApiError && error.status === 404) && failureCount < 3,
    staleTime: 5_000,
  })
}
