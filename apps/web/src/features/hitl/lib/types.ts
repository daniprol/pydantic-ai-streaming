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
