"use client"

import type React from "react"
import { createContext, useCallback, useContext, useState } from "react"

interface BreadcrumbDetail {
  /** Display label for this breadcrumb segment */
  label: string
  /** Optional link href */
  href?: string
}

interface BreadcrumbContextValue {
  /** Extra detail segment shown after the page-level breadcrumb (e.g. workflow name, run id) */
  detail: BreadcrumbDetail | null
  setDetail: (detail: BreadcrumbDetail | null) => void
}

const noop = () => {}
const defaultValue: BreadcrumbContextValue = { detail: null, setDetail: noop }

const BreadcrumbContext = createContext<BreadcrumbContextValue>(defaultValue)

export function BreadcrumbProvider({ children }: { children: React.ReactNode }) {
  const [detail, setDetailState] = useState<BreadcrumbDetail | null>(null)

  const setDetail = useCallback((d: BreadcrumbDetail | null) => {
    setDetailState(d)
  }, [])

  return (
    <BreadcrumbContext.Provider value={{ detail, setDetail }}>
      {children}
    </BreadcrumbContext.Provider>
  )
}

/** Returns breadcrumb detail context. Safe to call outside BreadcrumbProvider (returns no-op). */
export function useBreadcrumbDetail() {
  return useContext(BreadcrumbContext)
}
