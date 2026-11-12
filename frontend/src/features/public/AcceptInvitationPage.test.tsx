import { fakeEmail, fakePassword } from "../../test/data";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";
import type { components } from "../../api/schema";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import AcceptInvitationPage from "./AcceptInvitationPage";

const details = {
  organization_name: "Dental Example",
  full_name: "Testiva Testarić",
  email: fakeEmail("testiva", "example.test"),
  account_exists: false,
} satisfies components["schemas"]["PublicInvitationOut"];
const url = "/api/public/invitations/example-token";
const accept = `${url}/accept`;
const password = fakePassword();

function renderInvitation() {
  renderRoutes({ "/invite/:token": <AcceptInvitationPage /> }, "/invite/example-token");
}

it("accepts an invitation with a new password after checking its length and confirmation", async () => {
  const user = userEvent.setup();
  let requests = 0;
  server.use(
    http.get(url, () => HttpResponse.json(details)),
    http.post(accept, async ({ request }) => {
      requests += 1;
      expect(await request.json()).toEqual({ password });
      return HttpResponse.json({ status: "accepted" });
    }),
  );
  renderInvitation();
  const newPassword = await screen.findByLabelText("New password");
  const confirmation = screen.getByLabelText("Confirm password");
  const submit = screen.getByRole("button", { name: "Accept invitation" });
  expect(screen.getByText(/Dental Example/)).toBeInTheDocument();
  expect(screen.getByText(/Testiva Testarić/)).toBeInTheDocument();
  expect(screen.getByText(fakeEmail("testiva", "example.test"), { exact: false })).toBeInTheDocument();

  await user.type(newPassword, "short");
  await user.type(confirmation, "short");
  await user.click(submit);
  expect(screen.getByText("Use at least 12 characters.")).toBeInTheDocument();
  await user.clear(newPassword);
  await user.type(newPassword, password);
  await user.click(submit);
  expect(screen.getByText("Passwords must match.")).toBeInTheDocument();
  expect(requests).toBe(0);

  await user.clear(confirmation);
  await user.type(confirmation, password);
  await user.click(submit);
  expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
});

it("accepts with an existing account and TOTP code after the server challenges", async () => {
  const user = userEvent.setup();
  const existingPassword = fakePassword();
  const submissions: unknown[] = [];
  server.use(
    http.get(url, () => HttpResponse.json({ ...details, account_exists: true })),
    http.post(accept, async ({ request }) => {
      const body = (await request.json()) as components["schemas"]["AcceptInvitationIn"];
      submissions.push(body);
      if (body.password !== existingPassword) {
        return HttpResponse.json({ error: "invalid_credentials" }, { status: 401 });
      }
      if (body.code !== "123456") return HttpResponse.json({ error: "invalid_code" }, { status: 401 });
      return HttpResponse.json({ status: "accepted" });
    }),
  );
  renderInvitation();
  expect(await screen.findByText(/You already have an account/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Confirm password")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
  const currentPassword = screen.getByLabelText("Password");
  const submit = screen.getByRole("button", { name: "Accept invitation" });
  await user.type(currentPassword, "wrong");
  await user.click(submit);
  expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
  expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
  await user.clear(currentPassword);
  await user.type(currentPassword, existingPassword);
  await user.click(submit);
  const code = await screen.findByLabelText("Code");
  expect(screen.getByText("Enter the code from your authenticator app.")).toBeInTheDocument();

  await user.type(code, "000000");
  await user.click(submit);
  expect(await screen.findByText("Invalid code")).toBeInTheDocument();
  await user.clear(code);
  await user.type(code, "123456");
  await user.click(submit);
  expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
  expect(submissions).toEqual([
    { password: "wrong" },
    { password: existingPassword },
    { password: existingPassword, code: "000000" },
    { password: existingPassword, code: "123456" },
  ]);
});

it.each([
  [409, "account_exists_retry"],
  [401, "invalid_credentials"],
])("switches to the existing-account form when account creation races (%s %s)", async (status, error) => {
  const user = userEvent.setup();
  server.use(
    http.get(url, () => HttpResponse.json(details)),
    http.post(accept, () => HttpResponse.json({ error }, { status })),
  );
  renderInvitation();
  await user.type(await screen.findByLabelText("New password"), password);
  await user.type(screen.getByLabelText("Confirm password"), password);
  await user.click(screen.getByRole("button", { name: "Accept invitation" }));

  expect(await screen.findByText(/An account now exists for this email address/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Confirm password")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Password")).toHaveValue("");
});

it.each([
  [404, "not_found", "This invitation link is invalid."],
  [410, "invitation_expired", "This invitation has expired."],
  [410, "invitation_used", "This invitation has already been used."],
  [410, "invitation_revoked", "This invitation has been revoked."],
])("shows the message for %s %s without a password form", async (status, error, message) => {
  server.use(http.get(url, () => HttpResponse.json({ error }, { status })));
  renderInvitation();
  expect(await screen.findByText(message)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Accept invitation" })).not.toBeInTheDocument();
});

it("removes the form when an invitation is revoked after it was opened", async () => {
  const user = userEvent.setup();
  server.use(
    http.get(url, () => HttpResponse.json({ ...details, account_exists: true })),
    http.post(accept, () => HttpResponse.json({ error: "invitation_revoked" }, { status: 410 })),
  );
  renderInvitation();
  await user.type(await screen.findByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Accept invitation" }));

  expect(await screen.findByText("This invitation has been revoked.")).toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
});
