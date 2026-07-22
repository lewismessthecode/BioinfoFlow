import { serializePublicRuntimeConfig } from "@/lib/runtime/public-config"

export const dynamic = "force-dynamic"

export function GET() {
  const apiBaseUrl =
    process.env.BIOINFOFLOW_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000/api/v1"

  return new Response(serializePublicRuntimeConfig({ apiBaseUrl }), {
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "text/javascript; charset=utf-8",
    },
  })
}

