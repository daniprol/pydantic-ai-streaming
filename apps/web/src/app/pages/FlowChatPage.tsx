import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'

import { ApiError, createConversation } from '@/features/chat/api/client'
import { ChatPanel } from '@/features/chat/components/ChatPanel'
import { FLOWS, isFlow } from '@/features/chat/lib/flows'
import { useConversationMessages, useConversations, useDeleteConversation } from '@/features/conversations/hooks/useConversations'
import { AppSidebar } from '@/components/app-sidebar'
import { ChatLayout } from '@/components/ChatLayout'

export function FlowChatPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useParams()
  const flow = isFlow(params.flow) ? params.flow : 'basic'
  const conversationId = params.conversationId
  const conversationsQuery = useConversations(flow)
  const messagesQuery = useConversationMessages(flow, conversationId)
  const deleteMutation = useDeleteConversation(flow)
  const activeFlow = FLOWS.find((entry) => entry.id === flow)!
  const conversationMissing =
    Boolean(conversationId) &&
    messagesQuery.isError &&
    messagesQuery.error instanceof ApiError &&
    messagesQuery.error.status === 404
  const initialPrompt =
    location.state && typeof location.state === 'object' && 'initialPrompt' in location.state
      ? location.state.initialPrompt
      : undefined

  if (!isFlow(params.flow)) {
    return <Navigate to="/basic" replace />
  }

  if (conversationMissing) {
    return (
      <Navigate
        to="/not-found"
        replace
        state={{
          title: 'Conversation not found',
          description: 'The link may be wrong, or the conversation may no longer exist.',
          returnTo: `/${flow}`,
          returnLabel: 'Start a new conversation',
        }}
      />
    )
  }

  async function handleStartConversation(prompt: string) {
    const response = await createConversation(flow)
    navigate(`/${flow}/conversations/${response.conversation.id}`, {
      state: { initialPrompt: prompt },
    })
  }

  async function handleDeleteConversation(id: string) {
    await deleteMutation.mutateAsync(id)
    if (id === conversationId) {
      navigate(`/${flow}`, { replace: true })
    }
  }

  function handleInitialPromptConsumed() {
    if (initialPrompt === undefined) {
      return
    }

    navigate(location.pathname, { replace: true, state: null })
  }

  const sidebar = (
    <AppSidebar 
      flow={flow} 
      conversations={conversationsQuery.data?.items ?? []} 
      isLoading={conversationsQuery.isLoading} 
      onDelete={handleDeleteConversation}
    />
  )

  return (
    <ChatLayout sidebar={sidebar} title={activeFlow.label}>
      <ChatPanel
        key={`${flow}-${conversationId ?? 'draft'}`}
        flow={flow}
        conversationId={conversationId}
        initialData={messagesQuery.data}
        initialPrompt={typeof initialPrompt === 'string' ? initialPrompt : undefined}
        onInitialPromptConsumed={handleInitialPromptConsumed}
        onStartConversation={handleStartConversation}
      />
    </ChatLayout>
  )
}
