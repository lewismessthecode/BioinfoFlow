"use client"

import { Skeleton } from "@/components/ui/skeleton"
import { CardContent, CardRoot } from "@/components/bioinfoflow/card"

function StatCardSkeleton() {
  return (
    <CardRoot variant="workbench">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-9 w-16" />
          </div>
          <Skeleton className="h-4 w-4" />
        </div>
        <div className="flex gap-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-20" />
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

function SystemStatusSkeleton() {
  return (
    <CardRoot variant="workbench">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      </div>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="bif-workbench-panel space-y-2 p-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-32" />
          </div>
          <div className="bif-workbench-panel space-y-2 p-3">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-28" />
          </div>
        </div>
      </CardContent>
    </CardRoot>
  )
}

export function DashboardSkeleton() {
  return (
    <div className="grid gap-4">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(22rem,0.85fr)]">
        <RecentRunsTableSkeleton />
        <SystemStatusSkeleton />
      </div>
    </div>
  )
}
