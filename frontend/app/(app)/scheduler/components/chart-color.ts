const FALLBACK = "rgba(128, 128, 128,"

export function cssColorToRgba(input: string, alpha: number): string {
  if (typeof document === "undefined") return `${FALLBACK} ${alpha})`
  const probe = document.createElement("span")
  probe.style.color = input
  probe.style.display = "none"
  document.body.appendChild(probe)
  const computed = getComputedStyle(probe).color
  document.body.removeChild(probe)
  const nums = computed.match(/-?\d+(?:\.\d+)?/g)
  if (!nums || nums.length < 3) return `${FALLBACK} ${alpha})`
  const [r, g, b] = nums.map((n) => Math.round(parseFloat(n)))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
