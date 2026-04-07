import * as React from "react"
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"

interface ChatLayoutProps {
  sidebar: React.ReactNode
  children: React.ReactNode
  title?: string
}

export function ChatLayout({ sidebar, children, title }: ChatLayoutProps) {
  return (
    <SidebarProvider>
      {sidebar}
      <div className="flex h-screen max-h-screen flex-1 flex-col overflow-hidden bg-background">
        <header className="flex h-14 items-center gap-4 px-4 border-b border-border/50">
          <SidebarTrigger />
          {title && <h1 className="text-sm font-semibold text-foreground">{title}</h1>}
        </header>
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {children}
        </main>
      </div>
    </SidebarProvider>
  )
}
