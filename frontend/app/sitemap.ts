import type { MetadataRoute } from "next"

const siteUrl = "https://www.bioinfoflow.com"

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date()

  return [
    {
      url: "https://www.bioinfoflow.com",
      lastModified,
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${siteUrl}/demo`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.8,
    },
  ]
}
