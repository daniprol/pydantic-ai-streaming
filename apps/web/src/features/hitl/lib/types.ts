import { z } from 'zod'

import type { PendingToolCall } from '@/types/chat'

export const hitlDecisionPayloadSchema = z.object({
  title: z.string().optional(),
  description: z.string().optional(),
  acceptLabel: z.string().optional(),
  rejectLabel: z.string().optional(),
})

export const hitlApprovalPayloadSchema = z.object({
  title: z.string().optional(),
  description: z.string().optional(),
  confirmLabel: z.string().optional(),
  rejectLabel: z.string().optional(),
})

const formOptionSchema = z.object({
  value: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
})

const textFieldSchema = z.object({
  kind: z.enum(['text', 'email']),
  name: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
  example: z.union([z.string(), z.boolean()]).nullable().optional(),
  placeholder: z.string().nullable().optional(),
  required: z.boolean().optional(),
})

const textareaFieldSchema = z.object({
  kind: z.literal('textarea'),
  name: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
  example: z.union([z.string(), z.boolean()]).nullable().optional(),
  placeholder: z.string().nullable().optional(),
  required: z.boolean().optional(),
})

const selectFieldSchema = z.object({
  kind: z.literal('select'),
  name: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
  example: z.union([z.string(), z.boolean()]).nullable().optional(),
  placeholder: z.string().nullable().optional(),
  required: z.boolean().optional(),
  options: z.array(formOptionSchema).min(1),
})

const checkboxFieldSchema = z.object({
  kind: z.literal('checkbox'),
  name: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
  example: z.boolean().nullable().optional(),
  required: z.boolean().optional(),
})

export const hitlFormFieldSchema = z.discriminatedUnion('kind', [
  textFieldSchema,
  textareaFieldSchema,
  selectFieldSchema,
  checkboxFieldSchema,
])

export type HitlFormField = z.infer<typeof hitlFormFieldSchema>
export type HitlFormOption = z.infer<typeof formOptionSchema>

const humanFormJsonSchema = z.object({
  properties: z.object({
    title: z.object({ type: z.string().optional() }).optional(),
    description: z.object({ type: z.string().optional() }).optional(),
    submitLabel: z.object({ type: z.string().optional() }).optional(),
    cancelLabel: z.object({ type: z.string().optional() }).optional(),
    fields: z.object({
      items: z.object({
        oneOf: z.array(z.object({ $ref: z.string() })).optional(),
      }),
    }),
  }),
  $defs: z.record(z.string(), z.object({
    properties: z.record(z.string(), z.unknown()).optional(),
    required: z.array(z.string()).optional(),
  })).optional(),
})

export const hitlFormPayloadSchema = z.object({
  title: z.string().optional(),
  description: z.string().optional(),
  submitLabel: z.string().optional(),
  cancelLabel: z.string().optional(),
  fields: z.array(hitlFormFieldSchema).optional(),
  schema: z.record(z.string(), z.unknown()).optional(),
})

export interface ParsedHitlFormPayload {
  title?: string
  description?: string
  submitLabel?: string
  cancelLabel?: string
  fields: HitlFormField[]
}

export interface HitlResolutionSummary {
  approved?: boolean
  reason?: string
  result?: unknown
}

export type SupportedResolvedToolPart = {
  state: 'approval-responded' | 'output-available' | 'output-denied'
  toolCallId: string
  toolName?: string
  type: string
}

function toFieldSchema(definition: Record<string, unknown>): HitlFormField | null {
  const properties = definition.properties
  if (!properties || typeof properties !== 'object') {
    return null
  }

  const propertyMap = properties as Record<string, Record<string, unknown> | undefined>
  const kindProperty = propertyMap.kind
  const kind = typeof kindProperty?.const === 'string'
    ? kindProperty.const
    : Array.isArray(kindProperty?.enum) && typeof kindProperty.enum[0] === 'string'
      ? kindProperty.enum[0]
      : null

  if (!kind) {
    return null
  }

  const normalizedName = typeof propertyMap.name?.title === 'string' ? propertyMap.name.title.toLowerCase() : undefined
  if (typeof propertyMap.name?.title !== 'string' || !normalizedName) {
    return null
  }

  const label = typeof propertyMap.label?.title === 'string' ? propertyMap.label.title : normalizedName
  const common = {
    name: normalizedName,
    label,
    description: typeof propertyMap.description?.default === 'string' ? propertyMap.description.default : null,
    example: propertyMap.example?.default as string | boolean | null | undefined,
    required: Boolean(propertyMap.required?.default),
  }

  if (kind === 'text' || kind === 'email') {
    return hitlFormFieldSchema.parse({
      ...common,
      kind,
      placeholder: typeof propertyMap.placeholder?.default === 'string' ? propertyMap.placeholder.default : null,
    })
  }

  if (kind === 'textarea') {
    return hitlFormFieldSchema.parse({
      ...common,
      kind,
      placeholder: typeof propertyMap.placeholder?.default === 'string' ? propertyMap.placeholder.default : null,
    })
  }

  if (kind === 'checkbox') {
    return hitlFormFieldSchema.parse({
      ...common,
      kind,
      example: typeof propertyMap.example?.default === 'boolean' ? propertyMap.example.default : null,
    })
  }

  if (kind === 'select') {
    const optionsProperty = propertyMap.options
    const optionItems = Array.isArray(optionsProperty?.default)
      ? optionsProperty.default
      : null
    if (optionItems) {
      return hitlFormFieldSchema.parse({
        ...common,
        kind,
        placeholder: typeof propertyMap.placeholder?.default === 'string' ? propertyMap.placeholder.default : null,
        options: optionItems,
      })
    }
  }

  return null
}

function extractFieldsFromJsonSchema(schema: Record<string, unknown> | undefined): HitlFormField[] {
  const parsedSchema = humanFormJsonSchema.safeParse(schema)
  if (!parsedSchema.success) {
    return []
  }

  const defs = parsedSchema.data.$defs ?? {}
  const refs = parsedSchema.data.properties.fields?.items.oneOf ?? []
  const fields: HitlFormField[] = []

  for (const ref of refs) {
    const refName = ref.$ref.split('/').at(-1)
    if (!refName) {
      continue
    }
    const definition = defs[refName]
    if (!definition) {
      continue
    }

    const field = toFieldSchema(definition)
    if (field) {
      fields.push(field)
    }
  }

  return fields
}

export function isPendingToolCallPending(pendingToolCall: PendingToolCall): boolean {
  return pendingToolCall.status === 'pending'
}

export function getDecisionPayload(pendingToolCall: PendingToolCall) {
  return hitlDecisionPayloadSchema.parse(pendingToolCall.ui_payload_json)
}

export function getApprovalPayload(pendingToolCall: PendingToolCall) {
  return hitlApprovalPayloadSchema.parse(pendingToolCall.ui_payload_json)
}

export function getFormPayload(pendingToolCall: PendingToolCall): ParsedHitlFormPayload {
  const payload = hitlFormPayloadSchema.parse(pendingToolCall.ui_payload_json)
  return {
    cancelLabel: payload.cancelLabel,
    description: payload.description,
    fields: payload.fields ?? extractFieldsFromJsonSchema(payload.schema),
    submitLabel: payload.submitLabel,
    title: payload.title,
  }
}

export function getResolvedHitlSummary(pendingToolCall: PendingToolCall): HitlResolutionSummary {
  const resolution = pendingToolCall.resolution_json ?? {}

  if ('approved' in resolution || 'reason' in resolution) {
    return {
      approved: resolution.approved as boolean | undefined,
      reason: resolution.reason as string | undefined,
    }
  }

  return {
    result: resolution.result,
  }
}
