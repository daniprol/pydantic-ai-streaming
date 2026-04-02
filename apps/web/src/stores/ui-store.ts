import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

interface UIState {
  sessionId: string
  sidebarOpen: boolean
  setSidebarOpen: (isOpen: boolean) => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sessionId: crypto.randomUUID(),
      sidebarOpen: true,
      setSidebarOpen: (sidebarOpen) => {
        set({ sidebarOpen })
      },
    }),
    {
      name: 'streaming-chat-ui',
      storage: createJSONStorage(() => window.localStorage),
    },
  ),
)
