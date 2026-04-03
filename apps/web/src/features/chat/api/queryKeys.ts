import type { FlowType } from '@/types/chat'

export const chatQueryKeys = {
  conversations: (flow: FlowType) => ['conversations', flow] as const,
  conversationMessages: (flow: FlowType, conversationId: string) =>
    ['conversation-messages', flow, conversationId] as const,
}
