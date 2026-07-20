"use client"

import { useSyncExternalStore } from "react"

export const DEV_AVATAR_STORAGE_KEY = "bioinfoflow.avatar.dev"
const DEV_AVATAR_EVENT = "bioinfoflow:dev-avatar-change"

function readDevAvatarPreference(): string | null {
  if (typeof window === "undefined") return null
  return window.localStorage.getItem(DEV_AVATAR_STORAGE_KEY)
}

function notifyPreferenceChanged() {
  if (typeof window === "undefined") return
  window.dispatchEvent(new Event(DEV_AVATAR_EVENT))
}

export function writeDevAvatarPreference(value: string): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(DEV_AVATAR_STORAGE_KEY, value)
  notifyPreferenceChanged()
}

export function clearDevAvatarPreference(): void {
  if (typeof window === "undefined") return
  window.localStorage.removeItem(DEV_AVATAR_STORAGE_KEY)
  notifyPreferenceChanged()
}

function subscribeDevAvatarPreference(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined

  const handleStorage = (event: StorageEvent) => {
    if (event.key === DEV_AVATAR_STORAGE_KEY) listener()
  }
  window.addEventListener("storage", handleStorage)
  window.addEventListener(DEV_AVATAR_EVENT, listener)

  return () => {
    window.removeEventListener("storage", handleStorage)
    window.removeEventListener(DEV_AVATAR_EVENT, listener)
  }
}

export function useDevAvatarPreference(enabled = true): string | null {
  const value = useSyncExternalStore(
    subscribeDevAvatarPreference,
    readDevAvatarPreference,
    () => null,
  )
  return enabled ? value : null
}
