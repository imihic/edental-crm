import { describe, expect, it } from "vitest";
import i18n from "./index";

describe("i18n", () => {
  it("renders the default interface in English", () => {
    expect(i18n.resolvedLanguage).toBe("en");
    expect(i18n.t("auth.login.title")).toBe("Sign in");
  });
});
