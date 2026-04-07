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
      const latestUserMessage = [...messages].reverse().find((message) => message.role === 'user')
      const latestAssistantMessage = [...messages].reverse().find((message) => message.role === 'assistant')
      const trigger = body?.trigger ?? 'submit-message'
      const hitlResolution = body?.hitlResolution as
        | {
            assistantMessageId: string
            tool: string
            toolCallId: string
            output?: unknown
          }
        | undefined

      let requestMessages: UIConversationMessage[] = []

      if (trigger === 'submit-message') {
        if (hitlResolution) {
          requestMessages = [
            {
              id: hitlResolution.assistantMessageId,
              role: 'assistant',
              parts: [
                {
                  output: hitlResolution.output,
                  state: 'output-available',
                  toolCallId: hitlResolution.toolCallId,
                  type: `tool-${hitlResolution.tool}`,
                },
              ],
            },
          ]
          if (latestUserMessage) {
            requestMessages.push(latestUserMessage)
          }
        } else if (latestMessage?.role === 'assistant') {
          requestMessages = latestAssistantMessage ? [latestAssistantMessage] : []
        } else if (latestUserMessage) {
          requestMessages = [latestUserMessage]
        }
      }

      const nextBody = { ...body }
      delete nextBody.hitlResolution

      return {
        body: {
          ...nextBody,
          trigger,
          id,
          messages: requestMessages,
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
