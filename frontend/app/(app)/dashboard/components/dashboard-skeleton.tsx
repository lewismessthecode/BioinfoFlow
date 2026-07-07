"use client"

import { Skeleton } from "@/components/ui/skeleton"
import { CardContent, CardRoot } from "@/components/bioinfoflow/card"

function StatCardSkeleton() {
  return (
    <div className="min-h-[5.875rem] px-4 py-3 min-[360px]:min-h-[4.875rem] min-[360px]:px-3.5 min-[360px]:py-2.5 lg:min-h-[5.875rem] lg:px-4 lg:py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-7 w-14" />
        </div>
        <Skeleton className="h-7 w-7 rounded-md" />
      </div>
      <div className="mt-2.5 flex gap-4">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  )
}

function RecentRunsTableSkeleton() {
  return (
    <CardRoot variant="workbench">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-8 w-20" />
        </div>
      </div>
      <CardContent>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 py-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-5 w-16 rounded-full" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </CardContent>
    </CardRoot>
  )
}

function SystemStatusSkeleton() {
  return (
    <CardRoot variant="workbench">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      </div>
      <CardContent className="space-y-0 p-0">
        <div className="grid divide-y divide-border/60 md:grid-cols-2 md:divide-x md:divide-y-0">
          <div className="space-y-2 px-4 py-3">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-full" />
          </div>
          <div className="space-y-2 px-4 py-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        </div>
      </CardContent>
    </CardRoot>
  )
}

export function DashboardSkeleton() {
  return (
    <div className="grid gap-3">
      <CardRoot variant="workbench" className="overflow-hidden">
        <div className="bif-dashboard-metric-grid">
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
      </CardRoot>

      <SystemStatusSkeleton />
      <RecentRunsTableSkeleton />
    </div>
  )
}
