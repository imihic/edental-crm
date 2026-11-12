import { fakeEmail } from "../../test/data";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, expect, it } from "vitest";
import { resetCsrfToken } from "../../api/client";
import type { components } from "../../api/schema";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import StaffPage from "./StaffPage";

const center = { id: "00000000-0000-4000-8000-000000000001", name: "Central Clinic" };
const west = { id: "00000000-0000-4000-8000-000000000002", name: "West Clinic" };
const manager = {
  id: "00000000-0000-4000-8000-000000000003",
  full_name: "Testa Testić",
  email: fakeEmail("testa", "example.test"),
  roles: ["clinic_manager"],
  clinics: [center],
  is_active: true,
} satisfies components["schemas"]["StaffOut"];
const invitation = {
  id: "00000000-0000-4000-8000-000000000004",
  full_name: "Testiva Testarić",
  email: fakeEmail("testiva", "example.test"),
  roles: ["receptionist"],
  clinic_ids: [west.id],
  created_at: "2026-11-10T12:00:00Z",
  expires_at: "2026-11-13T12:00:00Z",
} satisfies components["schemas"]["InvitationItemOut"];

function renderStaff() {
  return renderRoutes({ "/staff": <StaffPage clinics={[center, west]} /> }, "/staff");
}

beforeEach(() => {
  resetCsrfToken();
  server.use(
    http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
    http.get("/api/staff", () => HttpResponse.json({ items: [manager] })),
    http.get("/api/invitations", () => HttpResponse.json({ items: [] })),
  );
});

it("invites a staff member and shows the one-time link only until the dialog closes", async () => {
  const user = userEvent.setup();
  let created = false;
  server.use(
    http.get("/api/invitations", () => HttpResponse.json({ items: created ? [invitation] : [] })),
    http.post("/api/invitations", async ({ request }) => {
      expect(request.headers.get("X-CSRF-Token")).toBe("t");
      expect(await request.json()).toEqual({
        email: fakeEmail("testiva", "example.test"),
        full_name: "Testiva Testarić",
        roles: ["receptionist"],
        clinic_ids: [west.id],
      });
      created = true;
      return HttpResponse.json(
        { id: invitation.id, url: "/invite/example-token", expires_at: invitation.expires_at },
        { status: 201 },
      );
    }),
  );
  renderStaff();
  await screen.findByRole("row", { name: /Testa Testić/ });
  await user.click(screen.getByRole("button", { name: "Invite" }));
  const dialog = await screen.findByRole("dialog", { name: "Invite a staff member" });
  await user.type(within(dialog).getByLabelText("Email"), fakeEmail("testiva", "example.test"));
  await user.type(within(dialog).getByLabelText("Full name"), "Testiva Testarić");
  await user.click(within(dialog).getByRole("checkbox", { name: "Receptionist" }));
  await user.click(within(dialog).getByLabelText("Clinics"));
  await user.click(await screen.findByRole("option", { name: "West Clinic" }));
  await user.click(within(dialog).getByRole("button", { name: "Invite" }));

  const link = `${window.location.origin}/invite/example-token`;
  expect(await within(dialog).findByLabelText("Invitation link")).toHaveValue(link);
  expect(within(dialog).getByText(/shown only once/)).toBeInTheDocument();
  expect(within(dialog).getByText(/Expires.*2026/)).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Copy link" }));
  expect(await navigator.clipboard.readText()).toBe(link);
  await user.click(within(dialog).getByRole("button", { name: "Done" }));

  expect(await screen.findByText(fakeEmail("testiva", "example.test"))).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Invite" }));
  expect(screen.queryByDisplayValue(link)).not.toBeInTheDocument();
});

it("explains the last-manager rule and leaves the edit open", async () => {
  const user = userEvent.setup();
  server.use(
    http.patch(`/api/staff/${manager.id}`, async ({ request }) => {
      expect(await request.json()).toEqual({ is_active: false });
      return HttpResponse.json({ error: "last_manager" }, { status: 409 });
    }),
  );
  renderStaff();
  const row = await screen.findByRole("row", { name: /Testa Testić/ });
  expect(row).toHaveTextContent("Clinic manager");
  expect(row).toHaveTextContent("Central Clinic");
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  const drawer = await screen.findByRole("dialog", { name: "Edit staff member" });
  await user.click(within(drawer).getByLabelText("Active"));
  await user.click(within(drawer).getByRole("button", { name: "Save" }));
  expect(await within(drawer).findByText(/at least one active clinic manager/)).toBeInTheDocument();
  expect(within(drawer).getByLabelText("Active")).not.toBeChecked();
  expect(row).toHaveTextContent("Active");
});

it("edits a name, roles and clinics, then refreshes the staff table", async () => {
  const user = userEvent.setup();
  let member: components["schemas"]["StaffOut"] = manager;
  const colleague = {
    id: "00000000-0000-4000-8000-000000000005",
    full_name: "Testiva Testić",
    email: fakeEmail("ih", "example.test"),
    roles: ["dentist"],
    clinics: [west],
    is_active: true,
  } satisfies components["schemas"]["StaffOut"];
  server.use(
    http.get("/api/staff", () => HttpResponse.json({ items: [member, colleague] })),
    http.patch(`/api/staff/${manager.id}`, async ({ request }) => {
      const body = (await request.json()) as components["schemas"]["StaffPatchIn"];
      expect(body).toEqual({
        full_name: "Testa Testarić",
        roles: expect.arrayContaining(["dentist", "clinic_manager"]),
        clinic_ids: [center.id, west.id],
      });
      expect(body.roles).toHaveLength(2);
      member = { ...manager, full_name: "Testa Testarić", roles: ["dentist", "clinic_manager"], clinics: [center, west] };
      return HttpResponse.json(member);
    }),
  );
  renderStaff();
  const oldRow = await screen.findByRole("row", { name: /Testa Testić/ });
  await user.click(within(oldRow).getByRole("button", { name: "Edit" }));
  const drawer = await screen.findByRole("dialog", { name: "Edit staff member" });
  const name = within(drawer).getByLabelText("Full name");
  await user.clear(name);
  await user.type(name, "Testa Testarić");
  await user.click(within(drawer).getByRole("checkbox", { name: "Dentist" }));
  await user.click(within(drawer).getByLabelText("Clinics"));
  await user.click(await screen.findByRole("option", { name: "West Clinic" }));
  await user.click(within(drawer).getByRole("button", { name: "Save" }));
  const row = await screen.findByRole("row", { name: /Testa Testarić/ });
  expect(row).toHaveTextContent("Dentist");
  expect(row).toHaveTextContent("West Clinic");
});

it("revokes a pending invitation and removes it from the list", async () => {
  const user = userEvent.setup();
  let revoked = false;
  server.use(
    http.get("/api/invitations", () => HttpResponse.json({ items: revoked ? [] : [invitation] })),
    http.delete(`/api/invitations/${invitation.id}`, () => {
      revoked = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  renderStaff();
  const row = await screen.findByRole("row", { name: (name) => name.includes(fakeEmail("testiva", "example.test")) });
  await user.click(within(row).getByRole("button", { name: "Revoke" }));
  expect(await screen.findByText("No pending invitations.")).toBeInTheDocument();
  expect(screen.queryByText(fakeEmail("testiva", "example.test"))).not.toBeInTheDocument();
});
