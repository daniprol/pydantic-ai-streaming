import * as React from "react"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import { Bot, Database, Zap, RefreshCcw, Search, Plus, Trash2 } from "lucide-react"
import { Link, useParams, useLocation } from "react-router-dom"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

interface Conversation {
  id: string
  title: string
}

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  conversations?: Conversation[]
  isLoading?: boolean
  flow: string
  onDelete?: (id: string) => Promise<void>
}

const navItems = [
  { title: "Basic", url: "/basic", icon: Bot, id: "basic" },
  { title: "DBOS", url: "/dbos", icon: Database, id: "dbos" },
  { title: "Temporal", url: "/temporal", icon: Zap, id: "temporal" },
  { title: "Replay", url: "/dbos-replay", icon: RefreshCcw, id: "dbos-replay" },
]

export function AppSidebar({ conversations, isLoading, flow, onDelete, ...props }: AppSidebarProps) {
  const params = useParams()
  const location = useLocation()
  const activeConversationId = params.conversationId
  const [searchQuery, setSearchQuery] = React.useState("")
  const [deletingId, setDeletingId] = React.useState<string | null>(null)

  const filteredConversations = conversations?.filter(conv => 
    (conv.title || "Untitled").toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleDelete = async () => {
    if (deletingId && onDelete) {
      await onDelete(deletingId)
      setDeletingId(null)
    }
  }

  return (
    <Sidebar {...props} className="border-r border-border/50 bg-sidebar/50">
      <SidebarHeader className="px-4 py-4">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold tracking-tight text-foreground/90">
              Pydantic AI
            </h2>
          </div>
          <SidebarMenuButton 
            asChild
            className="flex h-9 w-full items-center justify-start gap-2 rounded-lg border border-border/50 bg-background px-3 text-sm font-medium transition-colors hover:bg-accent"
          >
            <Link to={`/${flow}`}>
              <Plus className="h-4 w-4" />
              New chat
            </Link>
          </SidebarMenuButton>
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    asChild 
                    isActive={location.pathname.startsWith(item.url)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Link to={item.url}>
                      <item.icon className="h-4 w-4" />
                      <span className="text-sm font-medium">{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <div className="px-2 py-2">
          <Separator className="bg-border/50" />
        </div>

        <SidebarGroup>
          <div className="px-2 pb-3 pt-1">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground/50" />
              <Input
                type="search"
                placeholder="Search conversations..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 rounded-md border-none bg-muted/30 pl-8 text-xs placeholder:text-muted-foreground/40 focus-visible:ring-1 focus-visible:ring-ring/20"
              />
            </div>
          </div>
          <SidebarGroupContent>
            <SidebarMenu>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <SidebarMenuItem key={i} className="px-2 py-1.5">
                    <Skeleton className="h-3.5 w-full rounded-full bg-muted/50" />
                  </SidebarMenuItem>
                ))
              ) : (
                filteredConversations?.map((conv) => (
                  <SidebarMenuItem key={conv.id} className="group flex items-center pr-2">
                    <SidebarMenuButton 
                      asChild 
                      isActive={conv.id === activeConversationId}
                      className="h-8 flex-1 text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                    >
                      <Link to={`/${flow}/conversations/${conv.id}`}>
                        <span className="truncate text-xs font-normal">
                          {conv.title || 'Untitled conversation'}
                        </span>
                      </Link>
                    </SidebarMenuButton>
                    <button
                      onClick={() => setDeletingId(conv.id)}
                      className="ml-auto opacity-0 group-hover:opacity-100 p-1 rounded-md text-muted-foreground hover:text-destructive transition-all"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </SidebarMenuItem>
                ))
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />

      <AlertDialog open={!!deletingId} onOpenChange={(open) => !open && setDeletingId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete this conversation and all its messages. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sidebar>
  )
}
