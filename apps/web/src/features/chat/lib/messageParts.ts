import type { UIConversationMessage } from '@/types/chat'

export type ConversationPart = UIConversationMessage['parts'][number]

export type MessagePartSegment =
  | {
      kind: 'part'
      index: number
      part: ConversationPart
    }
  | {
      kind: 'tool-group'
      parts: ConversationPart[]
      startIndex: number
    }

const TOOL_LABELS: Record<string, string> = {
  ask_policy_researcher: 'Researching policy guidance',
  check_service_health: 'Checking service health',
  lookup_order_status: 'Checking order status',
  search_help_center: 'Searching the help center',
}

const TOOL_STATUS_LABELS: Record<string, string> = {
  'approval-requested': 'Needs approval',
  'approval-responded': 'Approved',
  'input-available': 'In progress',
  'input-streaming': 'Starting',
  'output-available': 'Done',
  'output-denied': 'Denied',
  'output-error': 'Error',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function getString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

function getPartType(part: ConversationPart): string | undefined {
  return isRecord(part) ? getString(part.type) : undefined
}

function toStartCase(value: string): string {
  return value
    .replaceAll(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function isTextPart(part: ConversationPart): part is ConversationPart & { text: string; type: 'text' } {
  return getPartType(part) === 'text' && isRecord(part) && typeof part.text === 'string'
}

export function isReasoningPart(part: ConversationPart): part is ConversationPart & { text: string; type: 'reasoning' } {
  return getPartType(part) === 'reasoning' && isRecord(part) && typeof part.text === 'string'
}

export function isToolPart(part: ConversationPart): boolean {
  if (!isRecord(part)) {
    return false
  }

  const type = getPartType(part)
  return Boolean(
    getString(part.toolCallId) ||
      type === 'dynamic-tool' ||
      type === 'tool-call' ||
      type === 'tool-result' ||
      type?.startsWith('tool-'),
  )
}

export function getToolName(part: ConversationPart): string | null {
  if (!isRecord(part)) {
    return null
  }

  const explicitName = getString(part.toolName) ?? getString(part.tool)
  if (explicitName) {
    return explicitName
  }

  const type = getPartType(part)
  if (type === 'tool-call' || type === 'tool-result') {
    return null
  }

  if (type?.startsWith('tool-')) {
    return type.slice(5)
  }

  return null
}

export function getToolLabel(part: ConversationPart): string {
  const toolName = getToolName(part)
  if (!toolName) {
    return 'Background step'
  }

  return TOOL_LABELS[toolName] ?? toStartCase(toolName)
}

export function getToolState(part: ConversationPart): string | undefined {
  if (!isRecord(part)) {
    return undefined
  }

  const state = getString(part.state)
  if (state) {
    return state
  }

  const type = getPartType(part)
  if (type === 'tool-call') {
    return 'input-available'
  }
  if (type === 'tool-result') {
    return 'output-available'
  }

  return undefined
}

export function getToolStatusLabel(part: ConversationPart): string {
  const state = getToolState(part)
  return state ? (TOOL_STATUS_LABELS[state] ?? 'Working') : 'Working'
}

export function isToolCompleted(part: ConversationPart): boolean {
  const state = getToolState(part)
  return state === 'approval-responded' || state === 'output-available'
}

export function getToolPartKey(part: ConversationPart, fallback: string): string {
  if (!isRecord(part)) {
    return fallback
  }

  return getString(part.toolCallId) ?? getString(part.id) ?? `${getToolName(part) ?? 'tool'}-${fallback}`
}

export function segmentMessageParts(parts: ConversationPart[]): MessagePartSegment[] {
  const segments: MessagePartSegment[] = []
  let index = 0

  while (index < parts.length) {
    const part = parts[index]

    if (isToolPart(part)) {
      const groupedParts: ConversationPart[] = []
      let nextIndex = index

      while (nextIndex < parts.length && isToolPart(parts[nextIndex])) {
        groupedParts.push(parts[nextIndex])
        nextIndex += 1
      }

      if (groupedParts.length >= 3) {
        segments.push({
          kind: 'tool-group',
          parts: groupedParts,
          startIndex: index,
        })
      } else {
        for (let toolIndex = index; toolIndex < nextIndex; toolIndex += 1) {
          segments.push({
            kind: 'part',
            index: toolIndex,
            part: parts[toolIndex],
          })
        }
      }

      index = nextIndex
      continue
    }

    segments.push({
      kind: 'part',
      index,
      part,
    })
    index += 1
  }

  return segments
}
