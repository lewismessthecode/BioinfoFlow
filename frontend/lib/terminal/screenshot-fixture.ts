export function isTerminalScreenshotFixtureEnabled(
  env?: Record<string, string | undefined>,
): boolean {
  const value = env
    ? env.NEXT_PUBLIC_BIOINFOFLOW_E2E_TERMINAL_FIXTURE
    : process.env.NEXT_PUBLIC_BIOINFOFLOW_E2E_TERMINAL_FIXTURE;
  return value === "1";
}
