import type { PendingToolCall } from '@/types/chat'

export interface HitlDecisionPayload {
  title?: string
  description?: string
  acceptLabel?: string
  rejectLabel?: string
}

export interface HitlFormField {
  name: string
  label?: string
  kind?: 'text' | 'textarea'
  required?: boolean
  placeholder?: string
}

export interface HitlFormPayload {
  title?: string
  description?: string
  submitLabel?: string
  schema?: {
    fields?: HitlFormField[]
  }
}

export interface HitlApprovalPayload {
  title?: string
  description?: string
  confirmLabel?: string
  rejectLabel?: string
}

export interface HitlResolutionSummary {
  approved?: boolean
  reason?: string
  result?: unknown
}

export type SupportedResolvedToolPart = {
  state: 'approval-responded' | 'output-available' | 'output-denied'
  toolCallId: string
  toolName?: string
  type: string
}

export function isPendingToolCallPending(pendingToolCall: PendingToolCall): boolean {
  return pendingToolCall.status === 'pending'
}

export function getDecisionPayload(pendingToolCall: PendingToolCall): HitlDecisionPayload {
  return pendingToolCall.ui_payload_json as HitlDecisionPayload
}

export function getFormPayload(pendingToolCall: PendingToolCall): HitlFormPayload {
  return pendingToolCall.ui_payload_json as HitlFormPayload
}

export function getApprovalPayload(pendingToolCall: PendingToolCall): HitlApprovalPayload {
  return pendingToolCall.ui_payload_json as HitlApprovalPayload
}

export function getResolvedHitlSummary(pendingToolCall: PendingToolCall): HitlResolutionSummary {
  const resolution = pendingToolCall.resolution_json ?? {}

  if ('approved' in resolution || 'reason' in resolution) {
    return {
      approved: resolution.approved as boolean | undefined,
      reason: resolution.reason as string | undefined,
    }
  }

  return {
    result: resolution.result,
  }
}
