export type TimePeriod = "morning" | "afternoon" | "evening" | "lateNight"

export function getTimePeriod(): TimePeriod {
  const hour = new Date().getHours()

  if (hour >= 5 && hour < 12) {
    return "morning"
  }

  if (hour >= 12 && hour < 17) {
    return "afternoon"
  }

  if (hour >= 17 && hour < 22) {
    return "evening"
  }

  return "lateNight"
}
