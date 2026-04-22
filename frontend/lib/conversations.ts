import type { AgentConversationRead } from "@/lib/types"

const conversationStorageKey = (projectId: string) => `bioinfoflow:conversation:${projectId}`
const conversationUpdatedEvent = "bioinfoflow:conversation-updated"

type ConversationUpdateDetail = {
  id: string
  project_id: string
  title?: string | null
  pinned?: boolean | null
  created_at?: string
  updated_at?: string
}

export const getStoredConversationId = (projectId: string) => {
  if (typeof window === "undefined") return null
  return window.localStorage.getItem(conversationStorageKey(projectId))
}

export const setStoredConversationId = (projectId: string, conversationId: string) => {
  if (typeof window === "undefined") return
  window.localStorage.setItem(conversationStorageKey(projectId), conversationId)
}

export const clearStoredConversationId = (projectId: string) => {
  if (typeof window === "undefined") return
  window.localStorage.removeItem(conversationStorageKey(projectId))
}

export const emitConversationUpdated = (conversation: ConversationUpdateDetail) => {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent<ConversationUpdateDetail>(conversationUpdatedEvent, {
      detail: conversation,
    }),
  )
}

export const listenForConversationUpdates = (
  listener: (conversation: ConversationUpdateDetail) => void,
) => {
  if (typeof window === "undefined") return () => {}

  const handleEvent = (event: Event) => {
    const customEvent = event as CustomEvent<ConversationUpdateDetail>
    if (!customEvent.detail) return
    listener(customEvent.detail)
  }

  window.addEventListener(conversationUpdatedEvent, handleEvent as EventListener)
  return () => {
    window.removeEventListener(conversationUpdatedEvent, handleEvent as EventListener)
  }
}

export const sortConversations = (
  conversations: AgentConversationRead[],
): AgentConversationRead[] =>
  [...conversations].sort((a, b) => {
    if (a.pinned && !b.pinned) return -1
    if (!a.pinned && b.pinned) return 1
    return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
  })
