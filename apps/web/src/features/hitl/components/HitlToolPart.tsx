import { PendingApprovalCard } from '@/features/hitl/components/PendingApprovalCard'
import { PendingDecisionCard } from '@/features/hitl/components/PendingDecisionCard'
import { PendingFormCard } from '@/features/hitl/components/PendingFormCard'
import { getToolName } from '@/features/chat/lib/messageParts'
import type { PendingToolCall } from '@/types/chat'

type SupportedToolPart = {
  approval?: { id: string }
  state: string
  toolCallId: string
  toolName?: string
}

type InputAvailableToolPart = SupportedToolPart & { state: 'input-available' }
type ApprovalRequestedToolPart = SupportedToolPart & {
  approval: { id: string }
  state: 'approval-requested'
}

function findPendingToolCall(
  pendingToolCalls: PendingToolCall[],
  toolCallId: string,
): PendingToolCall | undefined {
  return pendingToolCalls.find((pendingToolCall) => pendingToolCall.tool_call_id === toolCallId)
}

function isToolPartWithCallId(part: unknown): part is SupportedToolPart {
  return typeof part === 'object' && part !== null && 'toolCallId' in part && 'state' in part
}

function isApprovalRequestedToolPart(part: SupportedToolPart): part is ApprovalRequestedToolPart {
  return part.state === 'approval-requested' && 'approval' in part && typeof part.approval?.id === 'string'
}

function isInputAvailableToolPart(part: SupportedToolPart): part is InputAvailableToolPart {
  return part.state === 'input-available'
}

export function HitlToolPart({
  part,
  pendingToolCalls,
  disabled,
  onApprovalResponse,
  onToolOutput,
}: {
  part: unknown
  pendingToolCalls: PendingToolCall[]
  disabled: boolean
  onApprovalResponse: (approvalId: string, approved: boolean) => void
  onToolOutput: (toolName: string, toolCallId: string, output: unknown) => void
}) {
  if (!isToolPartWithCallId(part)) {
    return null
  }

  const pendingToolCall = findPendingToolCall(pendingToolCalls, part.toolCallId)
  const toolName = 'toolName' in part && typeof part.toolName === 'string' ? part.toolName : getToolName(part)

  if (!pendingToolCall || pendingToolCall.status !== 'pending') {
    return null
  }

  if (isApprovalRequestedToolPart(part) && part.approval && toolName) {
    return (
      <PendingApprovalCard
        confirmLabel={pendingToolCall?.ui_payload_json.confirmLabel as string | undefined}
        description={pendingToolCall?.ui_payload_json.description as string | undefined}
        disabled={disabled}
        onApprove={() => {
          onApprovalResponse(part.approval.id, true)
        }}
        onReject={() => {
          onApprovalResponse(part.approval.id, false)
        }}
        part={part}
        rejectLabel={pendingToolCall?.ui_payload_json.rejectLabel as string | undefined}
      />
    )
  }

  if (!isInputAvailableToolPart(part) || !toolName) {
    return null
  }

  if (pendingToolCall.kind === 'decision') {
    return (
      <PendingDecisionCard
        disabled={disabled}
        onAccept={() => {
          onToolOutput(toolName, part.toolCallId, { decision: 'accepted' })
        }}
        onReject={() => {
          onToolOutput(toolName, part.toolCallId, { decision: 'rejected' })
        }}
        pendingToolCall={pendingToolCall}
      />
    )
  }

  if (pendingToolCall.kind === 'form') {
    return (
      <PendingFormCard
        disabled={disabled}
        onSubmit={(values) => {
          onToolOutput(toolName, part.toolCallId, values)
        }}
        pendingToolCall={pendingToolCall}
      />
    )
  }

  return null
}
