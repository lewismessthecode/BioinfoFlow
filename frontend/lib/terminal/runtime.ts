export async function loadTerminalRuntime() {
  const [{ Terminal }, { FitAddon }] = await Promise.all([
    import("@xterm/xterm"),
    import("@xterm/addon-fit"),
  ])
  return { Terminal, FitAddon }
}
