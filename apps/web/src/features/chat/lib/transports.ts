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
      const trigger = body?.trigger ?? 'submit-message'
      const shouldSendLatestMessage = trigger === 'submit-message' && Boolean(latestMessage)

      return {
        body: {
          ...body,
          trigger,
          id,
          messages: latestMessage && shouldSendLatestMessage ? [latestMessage] : [],
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
