import Link from "next/link"
import { FileQuestion } from "@/lib/icons"
import { Button } from "@/components/ui/button"

export default function AppNotFound() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
        <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-muted/30 mb-4">
          <FileQuestion className="h-10 w-10 text-muted-foreground" />
        </div>
        <h2 className="text-lg font-semibold text-foreground mb-2">Page not found</h2>
        <p className="text-sm text-muted-foreground max-w-md mb-6">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Button asChild variant="default">
          <Link href="/dashboard">Go to dashboard</Link>
        </Button>
      </div>
    </div>
  )
}
