"use client"

import { Skeleton } from "@/components/ui/skeleton"

export default function Loading() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-6xl mx-auto">
        <div className="mb-6 space-y-2">
          <Skeleton className="h-7 w-28" />
          <Skeleton className="h-4 w-48" />
        </div>
        <div className="flex items-center gap-4 mb-6">
          <Skeleton className="h-10 w-72" />
          <Skeleton className="h-10 w-28" />
        </div>
        <div className="border border-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-7 gap-4 border-b border-border bg-secondary/50 px-4 py-3">
            {Array.from({ length: 7 }).map((_, index) => (
              <Skeleton key={index} className="h-4 w-full" />
            ))}
          </div>
          <div className="divide-y divide-border">
            {Array.from({ length: 6 }).map((_, row) => (
              <div key={row} className="grid grid-cols-7 gap-4 px-4 py-3">
                {Array.from({ length: 7 }).map((_, col) => (
                  <Skeleton key={col} className="h-4 w-full" />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
