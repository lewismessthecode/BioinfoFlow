import { describe, expect, it } from "vitest"
import { slugifyProjectPath } from "@/lib/utils"

describe("slugifyProjectPath", () => {
  it("converts a simple name to a lowercase slug", () => {
    expect(slugifyProjectPath("COVID Analysis")).toBe("covid-analysis")
  })

  it("replaces multiple non-alphanumeric characters with a single dash", () => {
    expect(slugifyProjectPath("RNA---seq   Pipeline")).toBe("rna-seq-pipeline")
  })

  it("trims leading and trailing dashes", () => {
    expect(slugifyProjectPath("  --hello world--  ")).toBe("hello-world")
  })

  it("preserves CJK characters", () => {
    expect(slugifyProjectPath("RNA-seq 分析")).toBe("rna-seq-分析")
  })

  it("handles a fully CJK name", () => {
    expect(slugifyProjectPath("基因组分析")).toBe("基因组分析")
  })

  it("returns an empty string for empty input", () => {
    expect(slugifyProjectPath("")).toBe("")
  })

  it("returns an empty string for whitespace-only input", () => {
    expect(slugifyProjectPath("   ")).toBe("")
  })

  it("falls back to untitled for punctuation-only input", () => {
    expect(slugifyProjectPath("!!!")).toBe("untitled")
    expect(slugifyProjectPath("@#$%")).toBe("untitled")
  })

  it("handles special characters and underscores", () => {
    expect(slugifyProjectPath("my_project@v2.0!")).toBe("my-project-v2-0")
  })

  it("handles mixed CJK and Latin characters", () => {
    expect(slugifyProjectPath("COVID 分析 Pipeline")).toBe("covid-分析-pipeline")
  })
})
