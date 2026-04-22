export function openInNewTab(url: string) {
  const nextWindow = window.open(url, "_blank", "noopener,noreferrer")
  if (nextWindow) {
    nextWindow.opener = null
  }
}
