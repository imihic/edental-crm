import { fakeEmail } from "../../test/data";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import PublicEnquiryPage from "./PublicEnquiryPage";

const routes = { "/enquiry/:key": <PublicEnquiryPage /> };
const formPath = "/api/public/enquiry-forms/sample";
const formInfo = { clinic_name: "Central Clinic", organization_name: "Dental", locale: "en" };

async function fillEnquiry(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByRole("textbox", { name: "Full name" }), "Testa Testić");
  await user.type(screen.getByRole("textbox", { name: "Email" }), fakeEmail("testa", "com.example.test"));
  await user.type(screen.getByRole("textbox", { name: "Message" }), "I'd like an appointment.");
}

it("submits the public enquiry form and thanks the visitor", async () => {
  const user = userEvent.setup();
  let submitted: unknown;
  server.use(
    http.get(formPath, () => HttpResponse.json(formInfo)),
    http.post(formPath + "/enquiries", async ({ request }) => {
      submitted = await request.json();
      return HttpResponse.json({ status: "received" }, { status: 202 });
    }),
  );
  const { container } = renderRoutes(routes, "/enquiry/sample");
  await fillEnquiry(user);
  await user.type(screen.getByRole("textbox", { name: "Preferred contact time" }), "After 5 pm");
  expect(screen.getByRole("checkbox", { name: "Marketing consent" })).not.toBeChecked();
  const website = container.querySelector('input[name="website"]');
  expect(website).toHaveAttribute("tabindex", "-1");
  expect(website).toHaveAttribute("autocomplete", "off");

  await user.click(screen.getByRole("button", { name: "Send enquiry" }));
  expect(await screen.findByText("Thank you. We received your enquiry.")).toBeVisible();
  expect(submitted).toEqual({
    full_name: "Testa Testić",
    phone: null,
    email: fakeEmail("testa", "com.example.test"),
    message: "I'd like an appointment.",
    preferred_contact_time: "After 5 pm",
    marketing_consent: false,
    website: "",
  });
});

it("shows not-available for an unknown key", async () => {
  server.use(
    http.get("/api/public/enquiry-forms/unknown", () =>
      HttpResponse.json({ error: "not_found" }, { status: 404 }),
    ),
  );
  renderRoutes(routes, "/enquiry/unknown");
  expect(await screen.findByRole("alert")).toHaveTextContent("This form is not available.");
});

it("renders in English without a session even with a legacy clinic locale", async () => {
  let authRequests = 0;
  server.use(
    http.all("/api/auth/*", () => {
      authRequests += 1;
      return HttpResponse.json({ error: "unauthenticated" }, { status: 401 });
    }),
    http.get(formPath, () => HttpResponse.json({ ...formInfo, locale: "hr" })),
  );
  renderRoutes(routes, "/enquiry/sample");
  expect(await screen.findByRole("heading", { name: "Central Clinic" })).toBeVisible();
  expect(screen.getByRole("main")).toHaveAttribute("lang", "en");
  expect(screen.getByRole("button", { name: "Send enquiry" })).toBeVisible();
  expect(authRequests).toBe(0);
});
