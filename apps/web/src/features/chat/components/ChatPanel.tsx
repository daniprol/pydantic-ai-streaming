import { useEffect, useRef, useState, type SyntheticEvent } from 'react'

import { useQueryClient } from '@tanstack/react-query'
import { useChat } from '@ai-sdk/react'

import { Conversation, ConversationContent, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Loader } from '@/components/ai-elements/loader'
import { chatQueryKeys } from '@/features/chat/api/queryKeys'
import {
  PromptInput,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputToolbar,
} from '@/components/ai-elements/prompt-input'
import { Part } from '@/Part'
import { createTransport } from '@/features/chat/lib/transports'
import type { ConversationMessagesResponse, FlowType, UIConversationMessage } from '@/types/chat'

export function ChatPanel({
  flow,
  conversationId,
  sessionId,
  initialData,
  initialPrompt,
  onInitialPromptConsumed,
  onStartConversation,
}: {
  flow: FlowType
  conversationId?: string
  sessionId: string
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
    sessionId,
    replayId: initialData?.active_replay_id ?? null,
  })

  const { messages, sendMessage, status, error, regenerate } = useChat({
    id: resolvedConversationId,
    messages: (initialData?.messages ?? []) as never,
    transport,
    resume: flow === 'dbos-replay' && Boolean(initialData?.active_replay_id),
    onFinish: async () => {
      await queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations(flow, sessionId) })
      if (conversationId) {
        await queryClient.invalidateQueries({
          queryKey: chatQueryKeys.conversationMessages(flow, conversationId, sessionId),
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

  function handleSubmit(event: SyntheticEvent) {
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

  return (
    <div className="flex h-full flex-col">
      <Conversation className="h-full min-h-0">
        <ConversationContent>
          {(messages as UIConversationMessage[]).map((message) => (
            <div key={message.id}>
              {message.parts.map((part, index) => (
                <Part
                  key={`${message.id}-${index}`}
                  part={part as never}
                  message={message as never}
                  status={status}
                  index={index}
                  regen={(messageId) => {
                    regenerate({ messageId }).catch((regenError: unknown) => {
                      console.error('Failed to regenerate message', regenError)
                    })
                  }}
                  lastMessage={message.id === messages.at(-1)?.id}
                />
              ))}
            </div>
          ))}
          {status === 'submitted' && <Loader />}
          {isCreatingConversation && <Loader />}
          {status === 'error' && error && (
            <div className="mx-4 my-2 rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error.message}
            </div>
          )}
          {draftError && (
            <div className="mx-4 my-2 rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {draftError}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="border-t border-border/60 bg-background/90 p-4 backdrop-blur">
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
            disabled={isCreatingConversation || status === 'submitted' || status === 'streaming'}
            placeholder="Ask about an order, service health, or support policy..."
          />
          <PromptInputToolbar>
            <div className="text-xs text-muted-foreground">
              {flow === 'dbos-replay'
                ? 'Replay mode can reconnect to active streams.'
                : 'Each flow uses the same chat UI with a different backend runner.'}
            </div>
            <PromptInputSubmit
              disabled={!input.trim() || isCreatingConversation}
              status={isCreatingConversation ? 'submitted' : status}
            />
          </PromptInputToolbar>
        </PromptInput>
      </div>
    </div>
  )
}
