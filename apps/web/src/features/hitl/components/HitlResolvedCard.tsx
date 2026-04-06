import { CheckCircle2Icon, ShieldCheckIcon, ShieldXIcon, XCircleIcon } from 'lucide-react'

import { Tool, ToolContent } from '@/components/ai-elements/tool'
import { getToolLabel } from '@/features/chat/lib/messageParts'
import {
  getApprovalPayload,
  getDecisionPayload,
  getFormPayload,
  getResolvedHitlSummary,
  type SupportedResolvedToolPart,
} from '@/features/hitl/lib/types'
import type { PendingToolCall } from '@/types/chat'

const resolvedStateLabels = {
  'approval-responded': 'Responded',
  'output-available': 'Completed',
  'output-denied': 'Denied',
} as const

type ResolvedToolHeaderProps = {
  state: keyof typeof resolvedStateLabels
  title: string
}

function ResolvedToolHeader({ state, title }: ResolvedToolHeaderProps) {
  const icon = state === 'approval-responded'
    ? <ShieldCheckIcon className="size-4 text-blue-500" />
    : state === 'output-denied'
      ? <XCircleIcon className="size-4 text-amber-500" />
      : <CheckCircle2Icon className="size-4 text-emerald-500" />

  return (
    <div className="flex items-center justify-between gap-4 p-3">
      <div className="flex items-center gap-2">
        {icon}
        <span className="font-medium text-sm">{title}</span>
      </div>
      <div className="rounded-full bg-secondary px-2.5 py-1 text-xs text-secondary-foreground">
        {resolvedStateLabels[state]}
      </div>
    </div>
  )
}

function ResultBlock({ label, value }: { label: string; value: unknown }) {
  if (value == null || value === '') {
    return null
  }

  return (
    <div className="space-y-1.5">
      <p className="font-medium text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <div className="rounded-lg bg-background/80 px-3 py-2 text-sm text-foreground/90">
        <pre className="whitespace-pre-wrap break-words font-sans">
          {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
        </pre>
      </div>
    </div>
  )
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
  const isDenied = pendingToolCall.status === 'denied' || part.state === 'output-denied'

  let title = toolLabel
  let description: string | undefined
  let resultValue: unknown = null

  if (pendingToolCall.kind === 'approval') {
    const payload = getApprovalPayload(pendingToolCall)
    title = payload.title ?? toolLabel
    description = payload.description
    resultValue = summary.reason ?? (summary.approved ? 'Approved' : 'Rejected')
  } else if (pendingToolCall.kind === 'decision') {
    const payload = getDecisionPayload(pendingToolCall)
    title = payload.title ?? toolLabel
    description = payload.description
    resultValue = summary.result
  } else {
    const payload = getFormPayload(pendingToolCall)
    title = payload.title ?? toolLabel
    description = payload.description
    resultValue = summary.result
  }

  const icon = pendingToolCall.kind === 'approval'
    ? summary.approved
      ? <ShieldCheckIcon className="size-4 text-emerald-500" />
      : <ShieldXIcon className="size-4 text-amber-500" />
    : isDenied
      ? <XCircleIcon className="size-4 text-amber-500" />
      : <CheckCircle2Icon className="size-4 text-emerald-500" />

  return (
    <Tool className="mt-3 rounded-xl border-border/60 bg-muted/15 shadow-none" defaultOpen>
      <ResolvedToolHeader state={part.state} title={title} />
      <ToolContent className="space-y-4 border-t border-border/40 bg-background/40">
        <div className="flex items-start gap-3 rounded-lg bg-muted/40 px-3 py-3">
          {icon}
          <div className="space-y-1 text-sm">
            <p className="font-medium text-foreground">{isDenied ? 'Human response recorded' : 'Human response applied'}</p>
            <p className="text-muted-foreground">{description ?? title}</p>
          </div>
        </div>
        <ResultBlock label={pendingToolCall.kind === 'form' ? 'Submitted data' : 'Response'} value={resultValue} />
        <div className="rounded-lg bg-background/80 px-3 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">Tool call:</span> {pendingToolCall.tool_call_id}
        </div>
      </ToolContent>
    </Tool>
  )
}
