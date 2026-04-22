"use client"

import { useTranslations } from "next-intl"
import {
  TableSkeleton,
  SkeletonCellLine,
  SkeletonCellBadge,
  SkeletonCellActions,
  type SkeletonColumn,
} from "@/components/ui/table-skeleton"
import { Skeleton } from "@/components/ui/skeleton"

export function RunsTableSkeleton() {
  const tRuns = useTranslations("runs")

  const columns: SkeletonColumn[] = [
    { header: "", width: "w-10", align: "center", cell: <Skeleton className="h-4 w-4 mx-auto" /> },
    { header: tRuns("runId"), cell: <SkeletonCellLine width="w-24" /> },
    { header: tRuns("workflow"), cell: <SkeletonCellLine width="w-32" /> },
    { header: tRuns("status"), cell: <SkeletonCellBadge /> },
    { header: tRuns("startTime"), cell: <SkeletonCellLine width="w-24" /> },
    { header: tRuns("duration"), cell: <SkeletonCellLine width="w-16" /> },
    { header: tRuns("samples"), cell: <SkeletonCellLine width="w-10" /> },
    {
      header: tRuns("actions"),
      align: "right",
      cell: <SkeletonCellActions buttons={[{ width: "w-8", rounded: true }, { width: "w-8", rounded: true }, { width: "w-8", rounded: true }]} />,
    },
  ]

  return <TableSkeleton columns={columns} />
}
