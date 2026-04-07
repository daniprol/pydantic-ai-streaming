import { useMemo } from 'react'

import { useForm } from '@tanstack/react-form'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { PendingToolCall } from '@/types/chat'

import { getFormPayload, type HitlFormField } from '@/features/hitl/lib/types'

type FormValue = string | boolean

function buildDefaultValues(fields: HitlFormField[]): Record<string, FormValue> {
  return Object.fromEntries(
    fields.map((field) => [field.name, field.kind === 'checkbox' ? Boolean(field.example ?? false) : '']),
  )
}

function FieldHint({ field }: { field: HitlFormField }) {
  const parts = [field.description, typeof field.example === 'string' ? `Example: ${field.example}` : null].filter(Boolean)
  if (parts.length === 0) {
    return null
  }

  return <p className="text-sm text-muted-foreground">{parts.join(' ')}</p>
}

function FieldControl({
  disabled,
  field,
  onBlur,
  onChange,
  value,
}: {
  disabled: boolean
  field: HitlFormField
  onBlur: () => void
  onChange: (value: FormValue) => void
  value: FormValue
}) {
  if (field.kind === 'textarea') {
    return (
      <Textarea
        className="min-h-24"
        disabled={disabled}
        id={field.name}
        onBlur={onBlur}
        onChange={(event) => {
          onChange(event.target.value)
        }}
        placeholder={field.placeholder ?? undefined}
        value={String(value ?? '')}
      />
    )
  }

  if (field.kind === 'select') {
    return (
      <Select
        disabled={disabled}
        onValueChange={(nextValue) => {
          onChange(nextValue)
        }}
        value={String(value ?? '')}
      >
        <SelectTrigger className="w-full" id={field.name}>
          <SelectValue placeholder={field.placeholder ?? 'Select an option'} />
        </SelectTrigger>
        <SelectContent>
          {field.options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  if (field.kind === 'checkbox') {
    return (
      <label className="flex items-start gap-3 rounded-xl border border-border/70 bg-background/80 px-3 py-3" htmlFor={field.name}>
        <Checkbox
          checked={Boolean(value)}
          disabled={disabled}
          id={field.name}
          onBlur={onBlur}
          onCheckedChange={(checked) => {
            onChange(Boolean(checked))
          }}
        />
        <span className="pt-0.5 text-sm text-foreground">{field.label}</span>
      </label>
    )
  }

  return (
    <Input
      disabled={disabled}
      id={field.name}
      onBlur={onBlur}
      onChange={(event) => {
        onChange(event.target.value)
      }}
      placeholder={field.placeholder ?? undefined}
      type={field.kind === 'email' ? 'email' : 'text'}
      value={String(value ?? '')}
    />
  )
}

export function PendingFormCard({
  pendingToolCall,
  disabled,
  onCancel,
  onSubmit,
}: {
  pendingToolCall: PendingToolCall
  disabled: boolean
  onCancel: () => void | Promise<void>
  onSubmit: (values: Record<string, FormValue>) => void | Promise<void>
}) {
  const payload = getFormPayload(pendingToolCall)
  const fields = useMemo(() => payload.fields, [payload.fields])

  const form = useForm({
    defaultValues: buildDefaultValues(fields),
    onSubmit: async ({ value }) => {
      await onSubmit(value)
    },
  })

  return (
    <Card className="mt-3 gap-4 rounded-2xl border-border/60 bg-muted/15 py-4 shadow-none">
      <CardHeader className="gap-1 px-5">
        <CardTitle className="text-base">{payload.title ?? 'Form required'}</CardTitle>
        {payload.description ? <CardDescription className="text-sm leading-6">{payload.description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="px-5">
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
                  if (field.required) {
                    if (field.kind === 'checkbox' && value !== true) {
                      return `${field.label} is required`
                    }

                    if (field.kind !== 'checkbox' && !String(value ?? '').trim()) {
                      return `${field.label} is required`
                    }
                  }
                  return undefined
                },
              }}
            >
              {(fieldApi) => (
                <div className="space-y-2.5">
                  {field.kind === 'checkbox' ? null : (
                    <div className="space-y-1">
                      <label className="font-medium text-sm text-foreground" htmlFor={field.name}>
                        {field.label}
                      </label>
                      <FieldHint field={field} />
                    </div>
                  )}
                  <FieldControl
                    disabled={disabled}
                    field={field}
                    onBlur={fieldApi.handleBlur}
                    onChange={fieldApi.handleChange}
                    value={fieldApi.state.value}
                  />
                  {field.kind === 'checkbox' ? <FieldHint field={field} /> : null}
                  {fieldApi.state.meta.errors.length > 0 ? (
                    <p className="text-destructive text-sm">{String(fieldApi.state.meta.errors[0])}</p>
                  ) : null}
                </div>
              )}
            </form.Field>
          ))}
          <CardFooter className="justify-between px-0 pb-0 pt-2">
            <Button disabled={disabled} onClick={onCancel} size="sm" type="button" variant="ghost">
              {payload.cancelLabel ?? 'Cancel'}
            </Button>
            <Button disabled={disabled} size="sm" type="submit">
              {payload.submitLabel ?? 'Submit'}
            </Button>
          </CardFooter>
        </form>
      </CardContent>
    </Card>
  )
}
