import { useSyncExternalStore } from "react"

type CelebrationsPreferenceMock = {
  getEnabled: () => boolean
  setEnabled: (enabled: boolean) => void
  reset: () => void
  subscribeToCelebrationsPreference: (listener: (enabled: boolean) => void) => () => void
  useCelebrationsEnabledPreference: () => boolean
}

export function createCelebrationsPreferenceMock(
  initialEnabled = true,
): CelebrationsPreferenceMock {
  let enabled = initialEnabled
  const subscribers = new Set<(enabled: boolean) => void>()

  const subscribeToCelebrationsPreference = (listener: (enabled: boolean) => void) => {
    subscribers.add(listener)
    return () => {
      subscribers.delete(listener)
    }
  }

  return {
    getEnabled: () => enabled,
    setEnabled: (nextEnabled: boolean) => {
      enabled = nextEnabled
      for (const listener of subscribers) {
        listener(nextEnabled)
      }
    },
    reset: () => {
      enabled = initialEnabled
      subscribers.clear()
    },
    subscribeToCelebrationsPreference,
    useCelebrationsEnabledPreference: () =>
      useSyncExternalStore(
        (callback) => {
          const listener = () => callback()
          subscribers.add(listener)
          return () => {
            subscribers.delete(listener)
          }
        },
        () => enabled,
        () => initialEnabled,
      ),
  }
}
