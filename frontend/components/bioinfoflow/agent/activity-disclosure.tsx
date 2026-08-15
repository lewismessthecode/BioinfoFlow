"use client"

import {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react"
import type { Dispatch, ReactNode, SetStateAction } from "react"

type ActivityDisclosureStore = {
  get: (key: string) => boolean | undefined
  set: (key: string, value: boolean) => void
}

const ActivityDisclosureContext = createContext<ActivityDisclosureStore | null>(
  null,
)

export function ActivityDisclosureProvider({ children }: { children: ReactNode }) {
  const [store] = useState<ActivityDisclosureStore>(() => {
    const values = new Map<string, boolean>()
    return {
      get: (key) => values.get(key),
      set: (key, value) => values.set(key, value),
    }
  })

  return (
    <ActivityDisclosureContext.Provider value={store}>
      {children}
    </ActivityDisclosureContext.Provider>
  )
}

export function useActivityDisclosure(
  key: string,
  defaultExpanded = false,
): [boolean, Dispatch<SetStateAction<boolean>>] {
  const store = useContext(ActivityDisclosureContext)
  const [expanded, setExpandedState] = useState(
    () => store?.get(key) ?? defaultExpanded,
  )
  const setExpanded = useCallback<Dispatch<SetStateAction<boolean>>>(
    (nextValue) => {
      setExpandedState((current) => {
        const next =
          typeof nextValue === "function" ? nextValue(current) : nextValue
        store?.set(key, next)
        return next
      })
    },
    [key, store],
  )

  return [expanded, setExpanded]
}
