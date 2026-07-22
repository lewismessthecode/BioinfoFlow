"use client"

import Link from "next/link"

export function DemoHistoryReplaceLink({
  href,
  children,
}: {
  href: string
  children: React.ReactNode
}) {
  return (
    <Link
      href={href}
      onClick={(event) => {
        event.preventDefault()
        window.location.replace(href)
      }}
    >
      {children}
    </Link>
  )
}
