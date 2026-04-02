import { Link, useLocation } from 'react-router-dom'

import { Button } from '@/components/ui/button'

interface NotFoundState {
  title?: string
  description?: string
  returnTo?: string
  returnLabel?: string
}

export function NotFoundPage() {
  const location = useLocation()
  const state = (location.state as NotFoundState | null) ?? null

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 py-10">
      <div className="max-w-md space-y-4 text-center">
        <p className="text-xs uppercase tracking-[0.25em] text-muted-foreground">404</p>
        <h1 className="text-3xl font-semibold">{state?.title ?? 'Page not found'}</h1>
        <p className="text-sm text-muted-foreground">
          {state?.description ?? 'The page you are looking for does not exist.'}
        </p>
        <Button asChild>
          <Link to={state?.returnTo ?? '/basic'}>{state?.returnLabel ?? 'Go to chat'}</Link>
        </Button>
      </div>
    </div>
  )
}
