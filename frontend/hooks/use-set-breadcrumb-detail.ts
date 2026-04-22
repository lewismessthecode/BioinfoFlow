"use client"

import { useEffect } from "react"
import { useBreadcrumbDetail } from "@/components/bioinfoflow/breadcrumb-context"

/**
 * Sets the breadcrumb detail segment for the current page.
 * Cleans up on unmount so stale labels don't persist.
 */
export function useSetBreadcrumbDetail(label: string | null | undefined, href?: string) {
  const { setDetail } = useBreadcrumbDetail()

  useEffect(() => {
    if (!label) return
    setDetail({ label, href })
    return () => setDetail(null)
  }, [label, href, setDetail])
}
