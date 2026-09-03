import { describe, expect, it } from "vitest";

import { isTerminalScreenshotFixtureEnabled } from "@/lib/terminal/screenshot-fixture";

describe("terminal screenshot fixture configuration", () => {
  it("is disabled when no test-only environment flag is present", () => {
    expect(isTerminalScreenshotFixtureEnabled({})).toBe(false);
    expect(
      isTerminalScreenshotFixtureEnabled({
        NEXT_PUBLIC_BIOINFOFLOW_E2E_TERMINAL_FIXTURE: "0",
      }),
    ).toBe(false);
  });

  it("enables only for the exact Playwright test flag", () => {
    expect(
      isTerminalScreenshotFixtureEnabled({
        NEXT_PUBLIC_BIOINFOFLOW_E2E_TERMINAL_FIXTURE: "1",
      }),
    ).toBe(true);
  });
});
