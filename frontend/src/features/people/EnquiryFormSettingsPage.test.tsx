import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";
import { resetCsrfToken } from "../../api/client";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import EnquiryFormSettingsPage from "./EnquiryFormSettingsPage";

it("copies the public link and regenerates after confirmation", async () => {
  resetCsrfToken();
  const user = userEvent.setup();
  const write = vi.spyOn(navigator.clipboard, "writeText");
  let regenerated: string | undefined;
  server.use(
    http.get("/api/auth/me", () =>
      HttpResponse.json({
        staff: { roles: ["clinic_manager"] },
        clinics: [{ id: "c1", name: "Central Clinic" }],
        organization_clinics: [{ id: "c1", name: "Central Clinic" }, { id: "c2", name: "West Clinic" }],
      }),
    ),
    http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
    http.get("/api/clinics/:id/enquiry-form", ({ params }) =>
      HttpResponse.json({ key: params.id, path: "/enquiry/" + params.id, enabled: true }),
    ),
    http.post("/api/clinics/:id/enquiry-form/regenerate", ({ params }) => {
      regenerated = String(params.id);
      return HttpResponse.json({ key: "new", path: "/enquiry/new", enabled: true });
    }),
  );
  renderRoutes({ "/settings/enquiry-form": <EnquiryFormSettingsPage /> }, "/settings/enquiry-form");
  expect(await screen.findByDisplayValue(window.location.origin + "/enquiry/c1")).toBeVisible();
  await user.click(screen.getByRole("tab", { name: "West Clinic" }));

  const url = window.location.origin + "/enquiry/c2";
  expect(await screen.findByDisplayValue(url)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Copy link" }));
  expect(write).toHaveBeenLastCalledWith(url);
  await user.click(screen.getByRole("button", { name: "Copy code" }));
  expect(write).toHaveBeenLastCalledWith(expect.stringContaining('<iframe src="' + url + '"'));

  const regenerate = screen.getByRole("button", { name: "Generate a new link" });
  await user.click(regenerate);
  const confirmation = await screen.findByRole("dialog");
  const dialog = within(confirmation);
  await waitFor(() => {
    expect(dialog.getByText("The old link and existing embeds will stop working immediately.")).toBeVisible();
  });
  await user.click(dialog.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(confirmation).not.toBeInTheDocument());
  expect(regenerated).toBeUndefined();
  await user.click(regenerate);
  await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Generate a new link" }));
  expect(await screen.findByDisplayValue(window.location.origin + "/enquiry/new")).toBeVisible();
  expect(regenerated).toBe("c2");
  write.mockRestore();
});
