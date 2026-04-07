import { describe, expect, it } from 'vitest'

import { getFormPayload } from '@/features/hitl/lib/types'
import type { PendingToolCall } from '@/types/chat'

function buildPendingToolCall(uiPayloadJson: Record<string, unknown>): PendingToolCall {
  return {
    approval_id: null,
    args_json: {},
    created_at: '2026-04-06T00:00:00Z',
    id: 'pending-form',
    kind: 'form',
    message_sequence: 1,
    pending_group_id: 'group-form',
    request_metadata_json: {},
    resolution_json: null,
    resolved_at: null,
    status: 'pending',
    tool_call_id: 'tool-form',
    tool_name: 'collect_human_form',
    ui_payload_json: uiPayloadJson,
  }
}

describe('getFormPayload', () => {
  it('prefers explicit typed fields from the payload', () => {
    const payload = getFormPayload(
      buildPendingToolCall({
        cancelLabel: 'Cancel',
        fields: [
          {
            kind: 'email',
            label: 'Work email',
            name: 'email',
            required: true,
          },
          {
            kind: 'checkbox',
            label: 'Consent',
            name: 'consent',
          },
        ],
        schema: { properties: {} },
        submitLabel: 'Submit',
        title: 'Preferences form',
      }),
    )

    expect(payload.title).toBe('Preferences form')
    expect(payload.fields).toHaveLength(2)
    expect(payload.fields[0].kind).toBe('email')
    expect(payload.fields[1].kind).toBe('checkbox')
  })
})
