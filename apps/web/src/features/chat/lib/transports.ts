import { DefaultChatTransport } from 'ai'

import type { FlowType, UIConversationMessage } from '@/types/chat'

interface TransportOptions {
  flow: FlowType
  conversationId: string
  sessionId: string
  replayId: string | null
}

export function createTransport({
  flow,
  conversationId,
  sessionId,
  replayId,
}: TransportOptions) {
  return new DefaultChatTransport({
    api: `/api/v1/flows/${flow}/chat?conversation_id=${conversationId}`,
    prepareSendMessagesRequest: ({
      messages,
      body,
      id,
    }: {
      messages: UIConversationMessage[]
      body?: Record<string, unknown>
      id?: string
    }) => {
      const latestMessage = messages.at(-1)
      return {
        headers: {
          'X-Session-Id': sessionId,
        },
        body: {
          ...body,
          trigger: body?.trigger ?? 'submit-message',
          id,
          messages: latestMessage ? [latestMessage] : [],
        },
      }
    },
    prepareReconnectToStreamRequest: () => {
      return {
        api: `/api/v1/flows/dbos-replay/streams/${replayId ?? conversationId}/replay`,
        headers: {
          'X-Session-Id': sessionId,
        },
      }
    },
  })
}
