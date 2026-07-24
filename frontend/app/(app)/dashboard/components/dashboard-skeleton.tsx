"use client"

import { Skeleton } from "@/components/ui/skeleton"
import { CardContent, CardRoot } from "@/components/bioinfoflow/card"

function StatCardSkeleton() {
  return (
    <CardRoot variant="workbench" className="h-full">
      <CardContent className="flex min-h-[6.75rem] flex-col justify-between gap-3 !p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 space-y-3">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-8 w-14" />
          </div>
          <Skeleton className="h-4 w-4 rounded-md" />
        </div>
        <div className="flex gap-4">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-3 w-16" />
        </div>
      </CardContent>
    </CardRoot>
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

function OperationsOverviewSkeleton() {
  return (
    <CardRoot variant="workbench" className="grid overflow-hidden xl:grid-cols-[0.8fr_minmax(0,1.35fr)_0.9fr]">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="min-w-0 border-t border-border/70 p-5 first:border-t-0 xl:border-l xl:border-t-0 xl:first:border-l-0">
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-5 w-14 rounded-full" />
          </div>
          <div className="mt-4 space-y-3">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        </div>
      ))}
    </CardRoot>
  )
}

export function DashboardSkeleton() {
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>

      <OperationsOverviewSkeleton />
      <RecentRunsTableSkeleton />
    </div>
  )
}
