const DAY_MS = 24 * 60 * 60 * 1000

export function formatSidebarRelativeDate(
  value?: string | null,
  locale = "en",
  now = new Date(),
) {
  const date = parseDate(value)
  if (!date) return null
  const dayDiff = calendarDayDiff(date, now)
  const zh = isZhLocale(locale)

  if (dayDiff <= 0) return zh ? "今天" : "today"
  if (dayDiff === 1) return zh ? "昨天" : "yesterday"
  if (dayDiff < 7) return zh ? `${dayDiff}天前` : `${dayDiff} days ago`

  const weekDiff = Math.max(1, Math.floor(dayDiff / 7))
  if (zh) return weekDiff === 1 ? "一周前" : `${weekDiff}周前`
  return weekDiff === 1 ? "1 week ago" : `${weekDiff} weeks ago`
}

export function formatTranscriptMessageDateTime(
  value?: string | null,
  locale = "en",
  now = new Date(),
) {
  const date = parseDate(value)
  if (!date) return null
  const dayDiff = calendarDayDiff(date, now)
  const recent = dayDiff >= 0 && dayDiff < 7
  const time = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date)

  if (recent) {
    const weekday = new Intl.DateTimeFormat(locale, { weekday: "long" }).format(date)
    return `${weekday} ${time}`
  }

  const monthDay = new Intl.DateTimeFormat(locale, {
    month: isZhLocale(locale) ? "long" : "short",
    day: "numeric",
  }).format(date)
  return `${monthDay} ${time}`
}

function parseDate(value?: string | null) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function calendarDayDiff(date: Date, now: Date) {
  return Math.round((startOfLocalDay(now).getTime() - startOfLocalDay(date).getTime()) / DAY_MS)
}

function startOfLocalDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function isZhLocale(locale: string) {
  return locale.toLowerCase().startsWith("zh")
}
