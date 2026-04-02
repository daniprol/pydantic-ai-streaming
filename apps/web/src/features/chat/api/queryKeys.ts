import type { FlowType } from '@/types/chat'

export const chatQueryKeys = {
  conversations: (flow: FlowType, sessionId: string) => ['conversations', flow, sessionId] as const,
  conversationMessages: (flow: FlowType, conversationId: string, sessionId: string) =>
    ['conversation-messages', flow, conversationId, sessionId] as const,
}
