import type { FlowType } from '@/types/chat'

export const FLOWS: { id: FlowType; label: string; blurb: string }[] = [
  {
    id: 'basic',
    label: 'Basic',
    blurb: 'Direct PydanticAI streaming',
  },
  {
    id: 'dbos',
    label: 'DBOS',
    blurb: 'Durable execution via DBOS',
  },
  {
    id: 'temporal',
    label: 'Temporal',
    blurb: 'Temporal-backed agent flow',
  },
  {
    id: 'dbos-replay',
    label: 'Replay',
    blurb: 'DBOS with resumable stream replay',
  },
]

export function isFlow(value: string | undefined): value is FlowType {
  return FLOWS.some((flow) => flow.id === value)
}
