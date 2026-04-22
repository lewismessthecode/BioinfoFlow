"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { ChatMessage } from "@/lib/chat-types"

/**
 * Manages auto-scroll behaviour for the chat message list.
 *
 * Tracks whether the user is at the bottom of the container, auto-scrolls
 * on new messages only when they are, and exposes an unread count + FAB
 * when the user has scrolled up.
 */
export function useChatScroll(messages: ChatMessage[]) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isUserAtBottomRef = useRef(true)
  const [showScrollFab, setShowScrollFab] = useState(false)

  // Track if user is at bottom of scroll container
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return
    const handleScroll = () => {
      const threshold = 100
      const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold
      isUserAtBottomRef.current = atBottom
      setShowScrollFab(!atBottom && messages.length > 0)
    }
    container.addEventListener("scroll", handleScroll, { passive: true })
    return () => container.removeEventListener("scroll", handleScroll)
  }, [messages.length])

  // Smart auto-scroll: only scroll to bottom if user was already at bottom
  useEffect(() => {
    if (isUserAtBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    setShowScrollFab(false)
  }, [])

  return {
    messagesEndRef,
    scrollContainerRef,
    scrollFabProps: {
      visible: showScrollFab,
      onClick: scrollToBottom,
    },
  }
}
