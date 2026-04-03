import { useEffect, useRef, useState, type FormEvent } from 'react'

import { useQueryClient } from '@tanstack/react-query'
import { useChat } from '@ai-sdk/react'

import { Conversation, ConversationContent, ConversationEmptyState, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Loader } from '@/components/ai-elements/loader'
import { chatQueryKeys } from '@/features/chat/api/queryKeys'
import {
  PromptInput,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  PromptInputActionAddScreenshot,
} from '@/components/ai-elements/prompt-input'
import type { PromptInputMessage } from '@/components/ai-elements/prompt-input'
import { ChatMessageParts } from '@/features/chat/components/MessagePart'
import { createTransport } from '@/features/chat/lib/transports'
import type { ConversationMessagesResponse, FlowType, UIConversationMessage } from '@/types/chat'

export function ChatPanel({
  flow,
  conversationId,
  initialData,
  initialPrompt,
  onInitialPromptConsumed,
  onStartConversation,
}: {
  flow: FlowType
  conversationId?: string
  initialData?: ConversationMessagesResponse
  initialPrompt?: string
  onInitialPromptConsumed?: () => void
  onStartConversation?: (prompt: string) => Promise<void>
}) {
  const [input, setInput] = useState('')
  const [draftError, setDraftError] = useState<string | null>(null)
  const [isCreatingConversation, setIsCreatingConversation] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const initialPromptSentRef = useRef(false)
  const queryClient = useQueryClient()
  const resolvedConversationId = conversationId ?? `draft-${flow}`

  const transport = createTransport({
    flow,
    conversationId: resolvedConversationId,
    replayId: initialData?.active_replay_id ?? null,
  })

  const { messages, sendMessage, status, error, regenerate, stop } = useChat({
    id: resolvedConversationId,
    messages: (initialData?.messages ?? []) as never,
    transport,
    resume: flow === 'dbos-replay' && Boolean(initialData?.active_replay_id),
    onFinish: async () => {
      await queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations(flow) })
      if (conversationId) {
        await queryClient.invalidateQueries({
          queryKey: chatQueryKeys.conversationMessages(flow, conversationId),
        })
      }
    },
  })

  useEffect(() => {
    textareaRef.current?.focus()
  }, [conversationId])

  useEffect(() => {
    if (!conversationId || !initialPrompt || initialPromptSentRef.current) {
      return
    }

    initialPromptSentRef.current = true
    onInitialPromptConsumed?.()
    sendMessage({ text: initialPrompt }).catch((sendError: unknown) => {
      console.error('Failed to send message', sendError)
    })
  }, [conversationId, initialPrompt, onInitialPromptConsumed, sendMessage])

  function handleSubmit(_: PromptInputMessage, event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const prompt = input.trim()
    if (!prompt) {
      return
    }

    if (!conversationId) {
      setDraftError(null)
      setIsCreatingConversation(true)
      onStartConversation?.(prompt)
        .then(() => {
          setInput('')
        })
        .catch((sendError: unknown) => {
          console.error('Failed to create conversation', sendError)
          setDraftError('Unable to start a new conversation right now.')
        })
        .finally(() => {
          setIsCreatingConversation(false)
        })
      return
    }

    setInput('')
    sendMessage({ text: prompt }).catch((sendError: unknown) => {
      console.error('Failed to send message', sendError)
    })
  }

  const chatMessages = messages as UIConversationMessage[]

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <Conversation className="flex-1 min-h-0">
        <ConversationContent className="mx-auto w-full max-w-3xl px-4 py-8">
          {chatMessages.length === 0 && status === 'ready' && !isCreatingConversation && (
            <ConversationEmptyState
              description="Ask about an order, service health, or support policy."
              title="Start a conversation"
            />
          )}
          {chatMessages.map((message) => (
            <div className="mb-6 last:mb-0" key={message.id}>
              <ChatMessageParts
                lastMessage={message.id === chatMessages.at(-1)?.id}
                message={message}
                regen={(messageId) => {
                  regenerate({ messageId }).catch((regenError: unknown) => {
                    console.error('Failed to regenerate message', regenError)
                  })
                }}
                status={status}
              />
            </div>
          ))}
          {status === 'submitted' && (
            <div className="flex justify-center py-4">
              <Loader />
            </div>
          )}
          {isCreatingConversation && (
            <div className="flex justify-center py-4">
              <Loader />
            </div>
          )}
          {status === 'error' && error && (
            <div className="mx-auto mt-4 max-w-2xl rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error.message}
            </div>
          )}
          {draftError && (
            <div className="mx-auto mt-4 max-w-2xl rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {draftError}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="sticky bottom-0 w-full border-t border-border/50 bg-background/95 px-4 pt-4 pb-6 backdrop-blur supports-[backdrop-filter]:bg-background/85">
        <div className="mx-auto max-w-3xl">
          <PromptInput onSubmit={handleSubmit}>
            <PromptInputTextarea
              ref={textareaRef}
              value={input}
              onChange={(event) => {
                setInput(event.target.value)
                if (draftError) {
                  setDraftError(null)
                }
              }}
              className="max-h-40"
              disabled={isCreatingConversation || status === 'submitted' || status === 'streaming'}
              placeholder="Ask about an order, service health, or support policy..."
            />

            <PromptInputFooter>
              <PromptInputTools>
                <PromptInputActionMenu>
                  <PromptInputActionMenuTrigger />
                  <PromptInputActionMenuContent>
                    <PromptInputActionAddAttachments />
                    <PromptInputActionAddScreenshot />
                  </PromptInputActionMenuContent>
                </PromptInputActionMenu>
              </PromptInputTools>
              <PromptInputSubmit
                disabled={isCreatingConversation || (!input.trim() && status !== 'submitted' && status !== 'streaming')}
                onStop={conversationId ? stop : undefined}
                status={isCreatingConversation ? 'submitted' : status}
              />
            </PromptInputFooter>
          </PromptInput>
        </div>
      </div>
    </div>
  )
}
