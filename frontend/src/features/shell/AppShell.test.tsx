import { fakeEmail } from "../../test/data";
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Me } from "../../api/auth";
import { renderRoutes } from "../../test/render";
import AppShell from "./AppShell";

function meWith(roles: string[]): Me {
  return {
    account: { id: "a1", email: fakeEmail("testa", "clinic.example.test") },
    staff: { id: "s1", full_name: "Testa Testić", roles },
    organization: { id: "o1", name: "Example Dental", timezone: "Europe/Zagreb", currency: "EUR", locale: "hr" },
    clinics: [],
    organizations_count: 1,
    totp_enrollment_required: false,
  } as unknown as Me;
}

describe("navigation", () => {
  it("hides manager-only navigation for a receptionist", () => {
    renderRoutes({ "/*": <AppShell me={meWith(["receptionist"])} /> }, "/");
    expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("href", "/patients");
    expect(screen.getByRole("link", { name: "Enquiries" })).toHaveAttribute("href", "/leads");
    expect(screen.queryByRole("link", { name: "Import" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Enquiry form" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Staff" })).not.toBeInTheDocument();
  });

  it("shows manager-only navigation for a clinic manager", () => {
    renderRoutes({ "/*": <AppShell me={meWith(["clinic_manager"])} /> }, "/");
    expect(screen.getByRole("link", { name: "Import" })).toHaveAttribute("href", "/imports");
    expect(screen.getByRole("link", { name: "Enquiry form" })).toHaveAttribute("href", "/settings/enquiry-form");
    expect(screen.getByRole("link", { name: "Staff" })).toHaveAttribute("href", "/staff");
  });
});
