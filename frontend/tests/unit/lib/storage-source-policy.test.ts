import { describe, expect, it } from "vitest"

import {
  allowedSourceKindsFromRoots,
  preferredSourceKindFromRoots,
} from "@/lib/storage-source-policy"

describe("storage-source-policy", () => {
  it("maps allowed roots to a deduplicated source-kind list in declaration order", () => {
    expect(
      allowedSourceKindsFromRoots([
        "reference",
        "project_data",
        "any_allowed_root",
      ]),
    ).toEqual(["reference", "project", "deliveries"])
  })

  it("returns the first allowed source kind as the preferred default", () => {
    expect(preferredSourceKindFromRoots(["shared_data", "project_data"])).toBe(
      "deliveries",
    )
  })

  it("returns undefined when no root restrictions were provided", () => {
    expect(allowedSourceKindsFromRoots(undefined)).toBeUndefined()
    expect(preferredSourceKindFromRoots([])).toBeUndefined()
  })
})
