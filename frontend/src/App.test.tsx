import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";
import App from "./App";
import { renderRoutes } from "./test/render";
import { server } from "./test/server";

it("opens a public enquiry without requesting a staff session", async () => {
  let sessionRequests = 0;
  server.use(
    http.get("/api/auth/me", () => {
      sessionRequests += 1;
      return HttpResponse.json({ error: "internal_error" }, { status: 500 });
    }),
    http.get("/api/public/enquiry-forms/example-key", () =>
      HttpResponse.json({ clinic_name: "Sample Clinic", organization_name: "Example Dental", locale: "en" }),
    ),
  );

  renderRoutes({ "/*": <App /> }, "/enquiry/example-key");

  expect((await screen.findAllByText(/Sample Clinic/)).length).toBeGreaterThan(0);
  expect(sessionRequests).toBe(0);
});

it("keeps staff pages behind the sign-in screen", async () => {
  server.use(
    http.get("/api/auth/me", () =>
      HttpResponse.json({ error: "unauthenticated" }, { status: 401 }),
    ),
  );

  renderRoutes({ "/*": <App /> }, "/leads");

  await screen.findByRole("textbox", { name: "Email" });
  expect(screen.getByTestId("where")).toHaveTextContent("/login");
});
