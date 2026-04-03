import { useEffect, useRef, useState, type FormEvent } from 'react'

import { useQueryClient } from '@tanstack/react-query'
import { useChat } from '@ai-sdk/react'

import { Conversation, ConversationContent, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Loader } from '@/components/ai-elements/loader'
import { chatQueryKeys } from '@/features/chat/api/queryKeys'
import {
  PromptInput,
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
import { Part } from '@/Part'
import { createTransport } from '@/features/chat/lib/transports'
import type { ConversationMessagesResponse, FlowType, UIConversationMessage } from '@/types/chat'
import { PlusIcon, ArrowUp } from 'lucide-react'

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

  const { messages, sendMessage, status, error, regenerate } = useChat({
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

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <Conversation className="flex-1 min-h-0">
        <ConversationContent className="mx-auto w-full max-w-3xl px-4 py-8">
          {(messages as UIConversationMessage[]).map((message) => (
            <div key={message.id} className="mb-6 last:mb-0">
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

      <div className="sticky bottom-0 w-full bg-gradient-to-t from-background via-background/95 to-transparent pb-6 pt-4 px-4">
        <div className="mx-auto max-w-3xl">
          <div className="relative overflow-hidden rounded-[26px] border border-border/50 bg-muted/30 p-1 px-2 shadow-sm transition-all focus-within:border-border/80 focus-within:bg-background focus-within:ring-1 focus-within:ring-ring/10">
            <PromptInput onSubmit={handleSubmit} className="border-none bg-transparent shadow-none">
                <div className="flex w-full items-end gap-1.5 px-1 py-1">
                    <PromptInputActionMenu>
                        <PromptInputActionMenuTrigger className="size-8 rounded-full border-none hover:bg-muted/50">
                            <PlusIcon className="size-4" />
                        </PromptInputActionMenuTrigger>
                        <PromptInputActionMenuContent>
                            <PromptInputActionAddAttachments />
                            <PromptInputActionAddScreenshot />
                        </PromptInputActionMenuContent>
                    </PromptInputActionMenu>

                    <PromptInputTextarea
                        ref={textareaRef}
                        value={input}
                        onChange={(event) => {
                            setInput(event.target.value)
                            if (draftError) {
                                setDraftError(null)
                            }
                        }}
                        className="min-h-[40px] max-h-60 flex-1 border-none bg-transparent py-2.5 text-[15px] focus-visible:ring-0"
                        disabled={isCreatingConversation || status === 'submitted' || status === 'streaming'}
                        placeholder="Message Pydantic AI..."
                    />

                    <PromptInputSubmit
                        disabled={!input.trim() || isCreatingConversation}
                        status={isCreatingConversation ? 'submitted' : status}
                        className="size-8 rounded-full bg-foreground text-background hover:bg-foreground/90 disabled:bg-muted disabled:text-muted-foreground flex items-center justify-center p-0 transition-all duration-200 shadow-sm"
                    >
                        <ArrowUp className="size-[18px]" strokeWidth={3} />
                    </PromptInputSubmit>
                </div>
            </PromptInput>
          </div>
          <p className="mt-3 text-center text-[10px] text-muted-foreground/40 font-medium tracking-tight">
            Pydantic AI Lab • Experimental UI
          </p>
        </div>
      </div>
    </div>
  )
}


