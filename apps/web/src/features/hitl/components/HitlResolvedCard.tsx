import { CheckCircle2Icon, CircleSlash2Icon, ShieldCheckIcon, ShieldXIcon, XCircleIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { getToolLabel } from '@/features/chat/lib/messageParts'
import {
  getApprovalPayload,
  getDecisionPayload,
  getFormPayload,
  getResolvedHitlSummary,
  type SupportedResolvedToolPart,
} from '@/features/hitl/lib/types'
import type { PendingToolCall } from '@/types/chat'

function SummaryShell({
  children,
  description,
  icon,
  status,
  title,
}: {
  children?: ReactNode
  description?: string
  icon: ReactNode
  status: string
  title: string
}) {
  return (
    <div className="mt-3 rounded-2xl border border-border/60 bg-muted/15 px-4 py-3 shadow-none">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5">{icon}</div>
          <div className="min-w-0 space-y-1">
            <p className="truncate font-medium text-sm text-foreground">{title}</p>
            <p className="text-sm text-muted-foreground">{status}</p>
            {description ? <p className="text-sm leading-6 text-muted-foreground/90">{description}</p> : null}
          </div>
        </div>
      </div>
      {children ? <div className="mt-3 border-t border-border/50 pt-3">{children}</div> : null}
    </div>
  )
}

function DataList({ entries }: { entries: Array<{ label: string; value: string }> }) {
  return (
    <dl className="space-y-2">
      {entries.map((entry) => (
        <div className="flex items-start justify-between gap-4" key={entry.label}>
          <dt className="text-sm text-muted-foreground">{entry.label}</dt>
          <dd className="max-w-[65%] text-right text-sm text-foreground">{entry.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function formatValue(value: unknown): string | null {
  if (value == null) {
    return null
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed ? trimmed : null
  }
  if (typeof value === 'number') {
    return String(value)
  }
  return null
}

function buildFormEntries(pendingToolCall: PendingToolCall): Array<{ label: string; value: string }> {
  const payload = getFormPayload(pendingToolCall)
  const result = getResolvedHitlSummary(pendingToolCall).result
  if (!result || typeof result !== 'object') {
    return []
  }

  const resultMap = result as Record<string, unknown>

  return payload.fields.flatMap((field) => {
    const formattedValue = formatValue(resultMap[field.name])
    return formattedValue ? [{ label: field.label, value: formattedValue }] : []
  })
}

export function HitlResolvedCard({
  part,
  pendingToolCall,
}: {
  part: SupportedResolvedToolPart
  pendingToolCall: PendingToolCall
}) {
  const toolLabel = getToolLabel(part)
  const summary = getResolvedHitlSummary(pendingToolCall)

  if (pendingToolCall.kind === 'approval') {
    const payload = getApprovalPayload(pendingToolCall)
    const approved = summary.approved === true && pendingToolCall.status === 'resolved'

    return (
      <SummaryShell
        icon={approved ? <ShieldCheckIcon className="size-4 text-emerald-500" /> : <ShieldXIcon className="size-4 text-amber-500" />}
        status={approved ? 'Approved' : 'Rejected'}
        title={payload.title ?? toolLabel}
      />
    )
  }

  if (pendingToolCall.kind === 'decision') {
    const payload = getDecisionPayload(pendingToolCall)
    const decision = summary.result && typeof summary.result === 'object' && 'decision' in (summary.result as Record<string, unknown>)
      ? (summary.result as Record<string, unknown>).decision
      : null
    const accepted = decision === 'accepted'

    return (
      <SummaryShell
        icon={accepted ? <CheckCircle2Icon className="size-4 text-emerald-500" /> : <XCircleIcon className="size-4 text-amber-500" />}
        description={payload.description}
        status={accepted ? 'Accepted' : 'Rejected'}
        title={payload.title ?? toolLabel}
      />
    )
  }

  const payload = getFormPayload(pendingToolCall)
  const cancelled = pendingToolCall.status === 'cancelled'
  const entries = buildFormEntries(pendingToolCall)

  return (
    <SummaryShell
      icon={cancelled ? <CircleSlash2Icon className="size-4 text-amber-500" /> : <CheckCircle2Icon className="size-4 text-emerald-500" />}
      description={payload.description}
      status={cancelled ? 'Cancelled' : 'Submitted'}
      title={payload.title ?? toolLabel}
    >
      {cancelled ? (
        <p className="text-sm text-muted-foreground">The form was cancelled and the conversation can continue.</p>
      ) : (
        <DataList entries={entries} />
      )}
    </SummaryShell>
  )
}
