import { Navigate, useParams } from 'react-router-dom'

import { ChatPanel } from '@/features/chat/components/ChatPanel'
import { FLOWS, isFlow } from '@/features/chat/lib/flows'
import { useConversationMessages, useConversations } from '@/features/conversations/hooks/useConversations'
import { ConversationSidebar } from '@/features/conversations/components/ConversationSidebar'
import { FlowNav } from '@/features/navigation/components/FlowNav'
import { useUIStore } from '@/stores/ui-store'

export function FlowChatPage() {
  const params = useParams()
  const sessionId = useUIStore((state) => state.sessionId)
  const flow = isFlow(params.flow) ? params.flow : 'basic'
  const conversationId = params.conversationId
  const conversationsQuery = useConversations(flow, sessionId)
  const messagesQuery = useConversationMessages(flow, conversationId, sessionId)
  const activeFlow = FLOWS.find((entry) => entry.id === flow)!

  if (!isFlow(params.flow)) {
    return <Navigate to="/basic" replace />
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <FlowNav activeFlow={flow} />
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col md:flex-row">
        <ConversationSidebar
          flow={flow}
          currentConversationId={conversationId}
          conversations={conversationsQuery.data?.items ?? []}
        />
        <main className="flex min-h-[70vh] flex-1 flex-col">
          <div className="border-b border-border/60 px-5 py-4">
            <p className="text-xs uppercase tracking-[0.25em] text-muted-foreground">{activeFlow.label}</p>
            <h2 className="text-xl font-semibold">{activeFlow.blurb}</h2>
          </div>
          <div className="min-h-0 flex-1">
            <ChatPanel
              key={`${flow}-${conversationId ?? 'draft'}`}
              flow={flow}
              conversationId={conversationId}
              sessionId={sessionId}
              initialData={messagesQuery.data}
            />
          </div>
        </main>
      </div>
    </div>
  )
}
