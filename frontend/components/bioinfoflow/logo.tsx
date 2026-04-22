import Image from "next/image"
import { cn } from "@/lib/utils"

interface LogoProps {
  size?: number
  className?: string
}

export function Logo({ size = 24, className }: LogoProps) {
  const brandAssetVersion = "20260408-3"
  const brandIconUrl = `/brand-icon.png?v=${brandAssetVersion}`

  return (
    <div className={cn("relative flex items-center justify-center", className)}>
      <Image
        src={brandIconUrl}
        width={size}
        height={size}
        alt=""
        aria-hidden="true"
        className="block select-none"
        draggable={false}
        unoptimized
      />
    </div>
  )
}
