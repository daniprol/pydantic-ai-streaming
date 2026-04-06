import { useMemo } from 'react'

import { useForm } from '@tanstack/react-form'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { PendingToolCall } from '@/types/chat'

import { getFormPayload, type HitlFormField } from '@/features/hitl/lib/types'

function buildDefaultValues(fields: HitlFormField[]): Record<string, string> {
  return Object.fromEntries(fields.map((field) => [field.name, '']))
}

function FieldControl({
  field,
  value,
  onBlur,
  onChange,
  disabled,
}: {
  field: HitlFormField
  value: string
  onBlur: () => void
  onChange: (value: string) => void
  disabled: boolean
}) {
  const commonProps = {
    disabled,
    id: field.name,
    onBlur,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      onChange(event.target.value)
    },
    placeholder: field.placeholder,
    value,
  }

  if (field.kind === 'textarea') {
    return <Textarea {...commonProps} className="min-h-24" />
  }

  return <Input {...commonProps} type="text" />
}

export function PendingFormCard({
  pendingToolCall,
  disabled,
  onSubmit,
}: {
  pendingToolCall: PendingToolCall
  disabled: boolean
  onSubmit: (values: Record<string, string>) => void | Promise<void>
}) {
  const payload = getFormPayload(pendingToolCall)
  const fields = useMemo(() => payload.schema?.fields ?? [], [payload.schema?.fields])

  const form = useForm({
    defaultValues: buildDefaultValues(fields),
    onSubmit: async ({ value }) => {
      await onSubmit(value)
    },
  })

  return (
    <Card className="mt-3 gap-4 border-border/60 bg-muted/20 py-4 shadow-none">
      <CardHeader className="gap-1">
        <CardTitle>{payload.title ?? 'Form required'}</CardTitle>
        {payload.description ? <CardDescription>{payload.description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            event.stopPropagation()
            form.handleSubmit().catch((error: unknown) => {
              console.error('Failed to submit HITL form', error)
            })
          }}
        >
          {fields.map((field) => (
            <form.Field
              key={field.name}
              name={field.name}
              validators={{
                onSubmit: ({ value }) => {
                  if (field.required && !String(value ?? '').trim()) {
                    return `${field.label ?? field.name} is required`
                  }
                  return undefined
                },
              }}
            >
              {(fieldApi) => (
                <div className="space-y-2">
                  <label className="font-medium text-sm" htmlFor={field.name}>
                    {field.label ?? field.name}
                  </label>
                  <FieldControl
                    disabled={disabled}
                    field={field}
                    onBlur={fieldApi.handleBlur}
                    onChange={fieldApi.handleChange}
                    value={String(fieldApi.state.value ?? '')}
                  />
                  {fieldApi.state.meta.errors.length > 0 ? (
                    <p className="text-destructive text-sm">{String(fieldApi.state.meta.errors[0])}</p>
                  ) : null}
                </div>
              )}
            </form.Field>
          ))}
          <CardFooter className="px-0 pb-0">
            <Button disabled={disabled} size="sm" type="submit">
              {payload.submitLabel ?? 'Submit'}
            </Button>
          </CardFooter>
        </form>
      </CardContent>
    </Card>
  )
}
