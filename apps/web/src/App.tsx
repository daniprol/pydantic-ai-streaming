import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppProviders } from '@/app/providers/AppProviders'
import { FlowChatPage } from '@/app/pages/FlowChatPage'
import { NotFoundPage } from '@/app/pages/NotFoundPage'

export default function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/basic" replace />} />
          <Route path="/not-found" element={<NotFoundPage />} />
          <Route path="/:flow" element={<FlowChatPage />} />
          <Route path="/:flow/conversations/:conversationId" element={<FlowChatPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}
