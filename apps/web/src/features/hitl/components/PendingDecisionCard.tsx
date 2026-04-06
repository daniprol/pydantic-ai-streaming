import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import type { PendingToolCall } from '@/types/chat'

import { getDecisionPayload } from '@/features/hitl/lib/types'

export function PendingDecisionCard({
  pendingToolCall,
  disabled,
  onAccept,
  onReject,
}: {
  pendingToolCall: PendingToolCall
  disabled: boolean
  onAccept: () => void
  onReject: () => void
}) {
  const payload = getDecisionPayload(pendingToolCall)

  return (
    <Card className="mt-3 gap-4 border-border/60 bg-muted/20 py-4 shadow-none">
      <CardHeader className="gap-1">
        <CardTitle>{payload.title ?? 'Decision required'}</CardTitle>
        {payload.description ? <CardDescription>{payload.description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="text-muted-foreground text-sm">
        Choose how the assistant should continue this step.
      </CardContent>
      <CardFooter className="gap-2">
        <Button disabled={disabled} onClick={onAccept} size="sm" type="button">
          {payload.acceptLabel ?? 'Accept'}
        </Button>
        <Button disabled={disabled} onClick={onReject} size="sm" type="button" variant="outline">
          {payload.rejectLabel ?? 'Reject'}
        </Button>
      </CardFooter>
    </Card>
  )
}
