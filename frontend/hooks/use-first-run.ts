"use client"

import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react"

import {
  bootstrapFirstRun,
  type FirstRunBootstrapResult,
} from "@/lib/first-run"

type FirstRunState = {
  data: FirstRunBootstrapResult | null
  isLoading: boolean
  error: Error | null
}

const FirstRunContext = createContext<FirstRunBootstrapResult | null>(null)
const FirstRunLoadingContext = createContext(false)

export function FirstRunProvider({
  value,
  isLoading = false,
  children,
}: {
  value: FirstRunBootstrapResult | null
  isLoading?: boolean
  children: React.ReactNode
}) {
  return createElement(
    FirstRunLoadingContext.Provider,
    { value: isLoading },
    createElement(FirstRunContext.Provider, { value }, children),
  )
}

export function useFirstRunContext() {
  return useContext(FirstRunContext)
}

export function useFirstRunLoadingContext() {
  return useContext(FirstRunLoadingContext)
}

export function useFirstRun(enabled: boolean): FirstRunState {
  const [state, setState] = useState<FirstRunState>({
    data: null,
    isLoading: enabled,
    error: null,
  })
  const request = useRef<Promise<FirstRunBootstrapResult> | null>(null)

  useEffect(() => {
    if (!enabled) return
    let active = true
    queueMicrotask(() => {
      if (active) {
        setState((current) => ({ ...current, isLoading: true, error: null }))
      }
    })
    const currentRequest = request.current ?? bootstrapFirstRun()
    request.current = currentRequest
    void currentRequest
      .then((data) => {
        if (active) setState({ data, isLoading: false, error: null })
      })
      .catch((caught) => {
        if (request.current === currentRequest) request.current = null
        if (!active) return
        setState({
          data: null,
          isLoading: false,
          error:
            caught instanceof Error
              ? caught
              : new Error("First-run bootstrap failed"),
        })
      })
    return () => {
      active = false
    }
  }, [enabled])

  return state
}
