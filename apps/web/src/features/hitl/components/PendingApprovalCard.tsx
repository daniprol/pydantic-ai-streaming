import type { ComponentProps } from 'react'

import {
  Confirmation,
  ConfirmationAccepted,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRejected,
  ConfirmationRequest,
  ConfirmationTitle,
} from '@/components/ai-elements/confirmation'

type ApprovalToolPart = {
  approval?: { approved?: boolean; id: string; reason?: string }
  state: 'approval-requested' | 'approval-responded' | 'output-denied' | 'output-available'
}

function hasApproval(
  part: ApprovalToolPart,
): part is ApprovalToolPart & { approval: { id: string; approved?: boolean; reason?: string } } {
  return 'approval' in part
}

type ConfirmationApproval = ComponentProps<typeof Confirmation>['approval']

export function PendingApprovalCard({
  part,
  description,
  confirmLabel,
  rejectLabel,
  disabled,
  onApprove,
  onReject,
}: {
  part: ApprovalToolPart
  description?: string
  confirmLabel?: string
  rejectLabel?: string
  disabled: boolean
  onApprove: () => void
  onReject: () => void
}) {
  if (!hasApproval(part)) {
    return null
  }

  return (
    <Confirmation approval={part.approval as ConfirmationApproval} className="mt-3 border-border/60 bg-muted/20" state={part.state}>
      <ConfirmationRequest>
        <ConfirmationTitle>{description ?? 'Review this action before it runs.'}</ConfirmationTitle>
        <ConfirmationActions>
          <ConfirmationAction disabled={disabled} onClick={onReject} variant="outline">
            {rejectLabel ?? 'Reject'}
          </ConfirmationAction>
          <ConfirmationAction disabled={disabled} onClick={onApprove}>
            {confirmLabel ?? 'Approve'}
          </ConfirmationAction>
        </ConfirmationActions>
      </ConfirmationRequest>
      <ConfirmationAccepted>
        <ConfirmationTitle>Approved</ConfirmationTitle>
      </ConfirmationAccepted>
      <ConfirmationRejected>
        <ConfirmationTitle>Rejected</ConfirmationTitle>
      </ConfirmationRejected>
    </Confirmation>
  )
}
