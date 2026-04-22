"use client"

import { useTranslations } from "next-intl"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent } from "@/components/ui/card"
import {
  TableSkeleton,
  GridSkeleton,
  SkeletonCellNameDesc,
  SkeletonCellLine,
  SkeletonCellBadge,
  SkeletonCellActions,
  type SkeletonColumn,
} from "@/components/ui/table-skeleton"

export function ImagesGridSkeleton() {
  return (
    <GridSkeleton>
      <Card className="group h-full flex flex-col">
        <CardContent className="p-4 flex-1 flex flex-col">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <Skeleton className="h-8 w-8 shrink-0 rounded-lg" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Skeleton className="h-5 w-14 rounded-full" />
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
          <div className="mt-auto pt-1">
            <Skeleton className="h-8 w-full" />
          </div>
        </CardContent>
      </Card>
    </GridSkeleton>
  )
}

export function ImagesTableSkeleton() {
  const tImages = useTranslations("images")

  const columns: SkeletonColumn[] = [
    { header: tImages("table.image"), cell: <SkeletonCellNameDesc descWidth="w-52" /> },
    { header: tImages("table.version"), cell: <SkeletonCellLine width="w-12" /> },
    { header: tImages("table.size"), cell: <SkeletonCellLine width="w-16" /> },
    { header: tImages("table.status"), cell: <SkeletonCellBadge /> },
    {
      header: tImages("table.actions"),
      align: "right",
      cell: <SkeletonCellActions buttons={[{ width: "w-20" }, { width: "w-8", rounded: true }]} />,
    },
  ]

  return <TableSkeleton columns={columns} />
}
