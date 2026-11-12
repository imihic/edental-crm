import { describe, expect, it } from "vitest";
import { isValidOib } from "./schemas";

describe("isValidOib", () => {
  it("accepts a valid OIB and rejects a wrong checksum", () => {
    expect(isValidOib("11111111119")).toBe(true);
    expect(isValidOib("11111111110")).toBe(false);
  });
  it("rejects wrong length and non-digits", () => {
    expect(isValidOib("1111111111")).toBe(false);
    expect(isValidOib("1111111111a")).toBe(false);
    expect(isValidOib("")).toBe(false);
  });
});
