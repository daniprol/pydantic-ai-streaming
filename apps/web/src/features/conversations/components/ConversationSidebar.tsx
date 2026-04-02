import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import type { ConversationSummary, FlowType } from '@/types/chat'

export function ConversationSidebar({
  flow,
  currentConversationId,
  conversations,
}: {
  flow: FlowType
  currentConversationId?: string
  conversations: ConversationSummary[]
}) {
  return (
    <aside className="w-full border-b border-border/60 bg-card/60 md:w-80 md:border-b-0 md:border-r">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-4">
        <div>
          <p className="text-xs uppercase tracking-[0.25em] text-muted-foreground">Conversations</p>
          <h2 className="font-medium">Current flow history</h2>
        </div>
        <Button asChild size="sm">
          <Link to={`/${flow}`}>New chat</Link>
        </Button>
      </div>
      <div className="flex max-h-[32rem] flex-col gap-2 overflow-y-auto p-3 md:max-h-[calc(100vh-8rem)]">
        {conversations.length === 0 && (
          <div className="rounded-lg border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
            No conversations yet for this flow.
          </div>
        )}
        {conversations.map((conversation) => (
          <Link
            key={conversation.id}
            to={`/${flow}/conversations/${conversation.id}`}
            className={`rounded-xl border px-3 py-3 transition ${
              conversation.id === currentConversationId
                ? 'border-primary bg-primary/5'
                : 'border-border/60 hover:border-primary/40 hover:bg-accent/50'
            }`}
          >
            <p className="truncate font-medium">{conversation.title ?? 'Untitled conversation'}</p>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
              {conversation.preview ?? 'No preview yet'}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              {new Date(conversation.updated_at).toLocaleString()}
            </p>
          </Link>
        ))}
      </div>
    </aside>
  )
}
