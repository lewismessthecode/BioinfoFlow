const STORAGE_KEY = "bioflow-recent-conversations"

interface RecentConversation {
  id: string
  title: string
  projectId: string
  projectName: string
  timestamp: number
}

export function getRecentConversations(): RecentConversation[] {
  if (typeof window === "undefined") return []
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return []
    return JSON.parse(stored) as RecentConversation[]
  } catch {
    return []
  }
}

