import {
  lastAssistantMessageIsCompleteWithApprovalResponses,
  lastAssistantMessageIsCompleteWithToolCalls,
} from 'ai'

export function lastAssistantMessageIsCompleteWithHitlResponses(
  options: Parameters<typeof lastAssistantMessageIsCompleteWithToolCalls>[0],
) {
  return (
    lastAssistantMessageIsCompleteWithApprovalResponses(options) ||
    lastAssistantMessageIsCompleteWithToolCalls(options)
  )
}
