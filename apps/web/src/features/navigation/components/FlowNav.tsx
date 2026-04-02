import { NavLink } from 'react-router-dom'

import { ModeToggle } from '@/components/mode-toggle'
import { Button } from '@/components/ui/button'
import { FLOWS } from '@/features/chat/lib/flows'
import type { FlowType } from '@/types/chat'

export function FlowNav({ activeFlow }: { activeFlow: FlowType }) {
  return (
    <header className="border-b border-border/70 bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">Streaming Chat Lab</p>
          <h1 className="font-semibold text-xl">Multi-flow PydanticAI playground</h1>
        </div>
        <div className="flex items-center gap-2">
          <nav className="flex flex-wrap gap-2">
            {FLOWS.map((flow) => (
              <Button key={flow.id} asChild variant={flow.id === activeFlow ? 'default' : 'outline'} size="sm">
                <NavLink to={`/${flow.id}`}>{flow.label}</NavLink>
              </Button>
            ))}
          </nav>
          <ModeToggle />
        </div>
      </div>
    </header>
  )
}
