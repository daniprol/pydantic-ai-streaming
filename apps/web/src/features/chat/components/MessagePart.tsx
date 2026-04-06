import { Actions, Action } from '@/components/ai-elements/actions'
import { Message, MessageContent } from '@/components/ai-elements/message'
import { Queue, QueueItem, QueueItemContent, QueueItemIndicator, QueueList, QueueSection, QueueSectionContent, QueueSectionLabel, QueueSectionTrigger } from '@/components/ai-elements/queue'
import { Reasoning, ReasoningContent, ReasoningTrigger } from '@/components/ai-elements/reasoning'
import { Response } from '@/components/ai-elements/response'
import { Tool } from '@/components/ai-elements/tool'
import { Badge } from '@/components/ui/badge'
import type { PendingToolCall, UIConversationMessage } from '@/types/chat'
import { CopyIcon, RefreshCcwIcon, WrenchIcon } from 'lucide-react'

import {
  getToolLabel,
  getToolPartKey,
  getToolStatusLabel,
  isReasoningPart,
  isTextPart,
  isToolCompleted,
  isToolPart,
  segmentMessageParts,
  type ConversationPart,
} from '@/features/chat/lib/messageParts'
import { HitlToolPart } from '@/features/hitl/components/HitlToolPart'

interface MessagePartProps {
  part: ConversationPart
  message: UIConversationMessage
  status: string
  regen: (id: string) => void
  index: number
  lastMessage: boolean
}

interface ChatMessagePartsProps {
  message: UIConversationMessage
  status: string
  regen: (id: string) => void
  lastMessage: boolean
  pendingToolCalls?: PendingToolCall[]
  hitlBusy?: boolean
  onApprovalResponse?: (approvalId: string, approved: boolean) => void
  onToolOutput?: (toolName: string, toolCallId: string, output: unknown) => void
}

function copy(text: string) {
  navigator.clipboard.writeText(text).catch((error: unknown) => {
    console.error('Error copying text:', error)
  })
}

function ToolStatusBadge({ part }: { part: ConversationPart }) {
  return (
    <Badge className="rounded-full px-2 py-0.5 font-medium text-[11px]" variant="secondary">
      {getToolStatusLabel(part)}
    </Badge>
  )
}

function ToolCall({ part }: { part: ConversationPart }) {
  return (
    <Tool className="mb-3 rounded-xl border-border/60 bg-muted/20 shadow-none" open={false}>
      <div className="flex items-center justify-between gap-3 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <WrenchIcon className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium text-foreground/85">{getToolLabel(part)}</span>
        </div>
        <ToolStatusBadge part={part} />
      </div>
    </Tool>
  )
}

function ToolCallGroup({ messageId, parts, startIndex }: { messageId: string; parts: ConversationPart[]; startIndex: number }) {
  return (
    <Queue className="rounded-xl border-border/60 bg-muted/15 px-2 py-2 shadow-none">
      <QueueSection defaultOpen={false}>
        <QueueSectionTrigger className="rounded-lg bg-transparent px-2 py-1.5 hover:bg-muted/60">
          <QueueSectionLabel count={parts.length} icon={<WrenchIcon className="size-4" />} label="background steps" />
        </QueueSectionTrigger>
        <QueueSectionContent>
          <QueueList className="mt-1">
            {parts.map((part, offset) => (
              <QueueItem className="px-2 py-1.5 hover:bg-transparent" key={getToolPartKey(part, `${messageId}-${startIndex + offset}`)}>
                <div className="flex items-center gap-2 text-sm">
                  <QueueItemIndicator completed={isToolCompleted(part)} />
                  <QueueItemContent className="text-foreground/80">{getToolLabel(part)}</QueueItemContent>
                  <span className="shrink-0 text-muted-foreground text-xs">{getToolStatusLabel(part)}</span>
                </div>
              </QueueItem>
            ))}
          </QueueList>
        </QueueSectionContent>
      </QueueSection>
    </Queue>
  )
}

export function MessagePart({ part, message, status, regen, index, lastMessage }: MessagePartProps) {
  if (isTextPart(part)) {
    return (
      <div className="py-4">
        <Message from={message.role}>
          <MessageContent>
            <Response>{part.text}</Response>
          </MessageContent>
        </Message>
        {message.role === 'assistant' && index === message.parts.length - 1 && (
          <Actions className="mt-1">
            <Action
              label="Retry"
              onClick={() => {
                regen(message.id)
              }}
            >
              <RefreshCcwIcon className="size-3" />
            </Action>
            <Action
              label="Copy"
              onClick={() => {
                copy(part.text)
              }}
            >
              <CopyIcon className="size-3" />
            </Action>
          </Actions>
        )}
      </div>
    )
  }

  if (isReasoningPart(part)) {
    return (
      <Reasoning className="w-full" isStreaming={status === 'streaming' && index === message.parts.length - 1 && lastMessage}>
        <ReasoningTrigger />
        <ReasoningContent>{part.text}</ReasoningContent>
      </Reasoning>
    )
  }

  if (isToolPart(part)) {
    return <ToolCall part={part} />
  }

  return null
}

export function ChatMessageParts({
  message,
  status,
  regen,
  lastMessage,
  pendingToolCalls = [],
  hitlBusy = false,
  onApprovalResponse,
  onToolOutput,
}: ChatMessagePartsProps) {
  const content = segmentMessageParts(message.parts).map((segment) => {
    if (segment.kind === 'tool-group') {
      return (
        <ToolCallGroup
          key={`tool-group-${message.id}-${segment.startIndex}`}
          messageId={message.id}
          parts={segment.parts}
          startIndex={segment.startIndex}
        />
      )
    }

    return (
      <div key={`${message.id}-${segment.index}`}>
        <MessagePart
          index={segment.index}
          lastMessage={lastMessage}
          message={message}
          part={segment.part}
          regen={regen}
          status={status}
        />
        {onApprovalResponse && onToolOutput ? (
          <HitlToolPart
            disabled={hitlBusy}
            onApprovalResponse={onApprovalResponse}
            onToolOutput={onToolOutput}
            part={segment.part}
            pendingToolCalls={pendingToolCalls}
          />
        ) : null}
      </div>
    )
  })

  return (
    <>{content}</>
  )
}
