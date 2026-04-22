"use client"

import { useTranslations } from "next-intl"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent } from "@/components/ui/card"
import {
  TableSkeleton,
  GridSkeleton,
  SkeletonCellNameDesc,
  SkeletonCellLine,
  SkeletonCellActions,
  type SkeletonColumn,
} from "@/components/ui/table-skeleton"

export function WorkflowsGridSkeleton() {
  return (
    <GridSkeleton>
      <Card className="group h-full flex flex-col">
        <CardContent className="p-4 flex-1 flex flex-col">
          <div className="flex items-start justify-between gap-2.5">
            <div className="flex items-center gap-2.5 min-w-0">
              <Skeleton className="h-8 w-8 shrink-0 rounded-lg" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Skeleton className="h-5 w-14 rounded-full" />
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-12" />
          </div>
          <div className="mt-auto pt-3">
            <div className="grid grid-cols-2 gap-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          </div>
        </CardContent>
      </Card>
    </GridSkeleton>
  )
}

export function WorkflowsTableSkeleton() {
  const tWorkflows = useTranslations("workflows")
  const tCommon = useTranslations("common")

  const columns: SkeletonColumn[] = [
    { header: tWorkflows("name"), cell: <SkeletonCellNameDesc nameWidth="w-40" descWidth="w-56" /> },
    { header: tWorkflows("source"), cell: <SkeletonCellLine width="w-16" /> },
    { header: tWorkflows("engine"), cell: <SkeletonCellLine width="w-16" /> },
    { header: tWorkflows("version"), cell: <SkeletonCellLine width="w-12" /> },
    { header: tWorkflows("lastModified"), cell: <SkeletonCellLine width="w-20" /> },
    {
      header: tCommon("actions"),
      align: "right",
      cell: <SkeletonCellActions buttons={[{ width: "w-16" }, { width: "w-8", rounded: true }]} />,
    },
  ]

  return <TableSkeleton columns={columns} />
}
