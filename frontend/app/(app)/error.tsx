"use client"

import { useEffect } from "react"
import { AlertTriangle } from "lucide-react"
import { EmptyState } from "@/components/ui/empty-state"

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="flex h-full items-center justify-center">
      <EmptyState
        icon={AlertTriangle}
        title="Something went wrong"
        description="An unexpected error occurred. Please try again."
        action={{ label: "Try again", onClick: reset }}
      />
    </div>
  )
}
