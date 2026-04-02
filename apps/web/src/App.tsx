import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppProviders } from '@/app/providers/AppProviders'
import { FlowChatPage } from '@/app/pages/FlowChatPage'

export default function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/basic" replace />} />
          <Route path="/:flow" element={<FlowChatPage />} />
          <Route path="/:flow/conversations/:conversationId" element={<FlowChatPage />} />
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}
