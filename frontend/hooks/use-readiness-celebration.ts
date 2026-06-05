"use client"

import { useCallback, useEffect, useRef } from "react"
import type {
  ReadinessCheck,
  ReadinessStatus,
} from "@/app/(app)/dashboard/components/dashboard-types"
import { apiRequest } from "@/lib/api"
import { celebrateReadinessTransitions } from "@/lib/celebrations"
import { listenForReadinessRefresh } from "@/lib/readiness-events"

type ReadinessSnapshot = Array<Pick<ReadinessCheck, "id" | "status">>

function snapshotChecks(checks: ReadinessCheck[]): ReadinessSnapshot {
  return checks.map((check) => ({ id: check.id, status: check.status }))
}

export function useReadinessCelebration() {
  const previousChecksRef = useRef<ReadinessSnapshot | null>(null)

  const refreshReadiness = useCallback(async () => {
    try {
      const { data } = await apiRequest<ReadinessStatus>("/system/readiness")
      celebrateReadinessTransitions(previousChecksRef.current, data.checks)
      previousChecksRef.current = snapshotChecks(data.checks)
    } catch {
      // Readiness celebrations are opportunistic; page-level data fetches surface real errors.
    }
  }, [])

  useEffect(() => {
    void refreshReadiness()
    return listenForReadinessRefresh(() => {
      void refreshReadiness()
    })
  }, [refreshReadiness])
}
