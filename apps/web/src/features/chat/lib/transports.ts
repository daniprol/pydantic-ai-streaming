import { DefaultChatTransport } from 'ai'

import { apiUrl } from '@/features/chat/api/base'
import type { FlowType, UIConversationMessage } from '@/types/chat'

interface TransportOptions {
  flow: FlowType
  conversationId: string
  replayId: string | null
}

export function createTransport({ flow, conversationId, replayId }: TransportOptions) {
  return new DefaultChatTransport({
    api: apiUrl(`/flows/${flow}/chat?conversation_id=${conversationId}`),
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
        api: apiUrl(`/flows/dbos-replay/streams/${replayId ?? conversationId}/replay`),
      }
    },
  })
}
