import { useEffect, useMemo, useRef, useState } from 'react'

import { useQueryClient } from '@tanstack/react-query'
import { useChat } from '@ai-sdk/react'
import { z } from 'zod'

import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation'
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
import type {
  ConversationMessagesResponse,
  FlowType,
  PendingToolCall,
  UIConversationMessage,
} from '@/types/chat'

type ChatHelpers = ReturnType<typeof useChat> & {
  addToolApprovalResponse: (payload: { approved: boolean; id: string }) => Promise<void>
}

function extractPendingToolConflictMessage(error: Error | undefined): string | null {
  if (!error?.message) {
    return null
  }

  try {
    const payload = JSON.parse(error.message) as {
      detail?: {
        message?: string
        pendingToolCallIds?: string[]
      }
    }
    if (!payload.detail?.message) {
      return null
    }

    return payload.detail.message
  } catch {
    return null
  }
}

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
  const [pendingToolCalls, setPendingToolCalls] = useState<PendingToolCall[]>(initialData?.pending_tool_calls ?? [])
  const [isSubmittingHitl, setIsSubmittingHitl] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const initialPromptSentRef = useRef(false)
  const queryClient = useQueryClient()
  const resolvedConversationId = conversationId ?? `draft-${flow}`

  const transport = createTransport({
    flow,
    conversationId: resolvedConversationId,
    replayId: initialData?.active_replay_id ?? null,
  })

  const hitlRequestSchema = useMemo(
    () => ({
      hitl_request: z.object({
        kind: z.enum(['approval', 'decision', 'form']),
        payload: z.record(z.string(), z.unknown()),
        status: z.enum(['pending', 'resolved', 'denied', 'cancelled']),
        toolCallId: z.string(),
        toolName: z.string(),
      }),
    }),
    [],
  )

  const {
    messages,
    sendMessage,
    status,
    error,
    regenerate,
    stop,
    addToolApprovalResponse,
    addToolOutput,
  } = useChat({
    id: resolvedConversationId,
    messages: (initialData?.messages ?? []) as never,
    dataPartSchemas: hitlRequestSchema,
    transport,
    resume: flow === 'dbos-replay' && Boolean(initialData?.active_replay_id),
    onData: () => {
      if (conversationId) {
        queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversationMessages(flow, conversationId) }).catch((queryError: unknown) => {
          console.error('Failed to refresh pending tool calls', queryError)
        })
      }
    },
    onFinish: () => {
      queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations(flow) }).catch((error: unknown) => {
        console.error('Failed to refresh conversations', error)
      })
      if (conversationId) {
        queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversationMessages(flow, conversationId) }).catch((queryError: unknown) => {
          console.error('Failed to refresh conversation messages', queryError)
        })
      }
    },
  }) as ChatHelpers

  useEffect(() => {
    setPendingToolCalls(initialData?.pending_tool_calls ?? [])
  }, [initialData?.pending_tool_calls])

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

  function handleSubmit(_: PromptInputMessage, event: { preventDefault(): void }) {
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
  const isBusy = isCreatingConversation || status === 'submitted' || status === 'streaming' || isSubmittingHitl
  const pendingToolConflictMessage = extractPendingToolConflictMessage(error)

  function markPendingToolCallResolved(toolCallId: string, status: PendingToolCall['status']) {
    setPendingToolCalls((currentPendingToolCalls) =>
      currentPendingToolCalls.map((pendingToolCall) =>
        pendingToolCall.tool_call_id === toolCallId ? { ...pendingToolCall, status } : pendingToolCall,
      ),
    )
  }

  function handleApprovalResponse(approvalId: string, approved: boolean) {
    setDraftError(null)
    setIsSubmittingHitl(true)
    void Promise.resolve(
      addToolApprovalResponse({
        approved,
        id: approvalId,
      }),
    )
      .finally(() => {
        setIsSubmittingHitl(false)
      })
  }

  function handleToolOutput(toolName: string, toolCallId: string, output: unknown) {
    setDraftError(null)
    setIsSubmittingHitl(true)
    const nextStatus = typeof output === 'object' && output !== null && 'status' in (output as Record<string, unknown>) && (output as Record<string, unknown>).status === 'cancelled'
      ? 'cancelled'
      : 'resolved'
    markPendingToolCallResolved(toolCallId, nextStatus)
    void Promise.resolve(
      addToolOutput({
        tool: toolName as never,
        toolCallId,
        output: output as never,
      }),
    )
      .then(() => sendMessage())
      .finally(() => {
        setIsSubmittingHitl(false)
      })
  }

  function handleFormCancel(toolName: string, toolCallId: string) {
    handleToolOutput(toolName, toolCallId, { status: 'cancelled' })
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <Conversation className="min-h-0 flex-1">
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
                hitlBusy={isSubmittingHitl}
                lastMessage={message.id === chatMessages.at(-1)?.id}
                message={message}
                onApprovalResponse={handleApprovalResponse}
                onFormCancel={handleFormCancel}
                onToolOutput={handleToolOutput}
                pendingToolCalls={pendingToolCalls}
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
              {pendingToolConflictMessage ?? 'Unable to send your message right now.'}
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

      <div className="shrink-0 border-t border-border/50 bg-background/95 px-4 pt-4 pb-6 backdrop-blur supports-[backdrop-filter]:bg-background/85">
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
              disabled={isBusy}
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
                disabled={
                  isCreatingConversation || isSubmittingHitl || (!input.trim() && status !== 'submitted' && status !== 'streaming')
                }
                onStop={
                  conversationId
                    ? () => {
                        stop().catch((stopError: unknown) => {
                          console.error('Failed to stop stream', stopError)
                        })
                      }
                    : undefined
                }
                status={isBusy ? 'submitted' : status}
              />
            </PromptInputFooter>
          </PromptInput>
        </div>
      </div>
    </div>
  )
}
