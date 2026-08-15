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
  if (dayDiff < 14) return zh ? "一周前" : "1 week ago"

  return new Intl.DateTimeFormat(locale, {
    month: isZhLocale(locale) ? "long" : "short",
    day: "numeric",
  }).format(date)
}

export function formatAbsoluteDateTime(value?: string | null, locale = "en") {
  const date = parseDate(value)
  if (!date) return null
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: isZhLocale(locale) ? "long" : "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date)
}

export function formatAgentEndTime(value?: string | null, locale = "en") {
  const date = parseDate(value)
  if (!date) return null
  return new Intl.DateTimeFormat(locale, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

export function formatAgentDuration(
  startedAt?: string | null,
  completedAt?: string | null,
  locale = "en",
) {
  const started = parseDate(startedAt)
  const completed = parseDate(completedAt)
  if (!started || !completed) return null
  const milliseconds = completed.getTime() - started.getTime()
  if (milliseconds < 0) return null

  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 })
  if (milliseconds < 1000) return `${number.format(milliseconds)} ms`
  if (milliseconds < 60_000) {
    return `${number.format(milliseconds / 1000)} s`
  }
  const totalSeconds = Math.round(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${number.format(minutes)}m ${number.format(seconds)}s`
}

export function dateTimeAttribute(value?: string | null) {
  return parseDate(value) ? value ?? undefined : undefined
}

function parseDate(value?: string | null) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function calendarDayDiff(date: Date, now: Date) {
  return Math.round(
    (startOfLocalDay(now).getTime() - startOfLocalDay(date).getTime()) / DAY_MS,
  )
}

function startOfLocalDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function isZhLocale(locale: string) {
  return locale.toLowerCase().startsWith("zh")
}
