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

function SystemStatusSkeleton() {
  return (
    <CardRoot variant="workbench" className="h-full">
      <div className="px-4 pb-2 pt-3.5">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      </div>
      <CardContent className="!pt-0">
        <div className="grid gap-5 md:grid-cols-2">
          <div className="space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-full" />
          </div>
          <div className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        </div>
      </CardContent>
    </CardRoot>
  )
}

function SchedulerSummarySkeleton() {
  return (
    <CardRoot variant="workbench" className="h-full">
      <div className="px-4 pb-2 pt-3.5">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-7 w-7 rounded-md" />
        </div>
      </div>
      <CardContent className="flex flex-col gap-4 !pt-0">
        <div className="space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-12" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </CardContent>
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

      <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,0.75fr)]">
        <SystemStatusSkeleton />
        <SchedulerSummarySkeleton />
      </div>
      <RecentRunsTableSkeleton />
    </div>
  )
}
