import { fakeEmail } from "../../test/data";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { resetCsrfToken } from "../../api/client";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import PatientDetailPage from "./PatientDetailPage";
import type { EnquiryOut } from "./api";

const baseDetail = {
  id: "p1",
  first_name: "Testm",
  last_name: "Testić",
  date_of_birth: "1990-05-01",
  phone: "+12025550105",
  email: fakeEmail("m", "com.example.test"),
  oib_masked: "*******1119",
  address: null,
  notes: null,
  preferred_clinic: null,
  preferred_language: "hr",
  guardians: [] as unknown[],
  guardian_of: [] as unknown[],
  age: 36,
  is_minor: false,
  consent: { marketing: "unknown" },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const routes = { "/patients/:id": <PatientDetailPage /> };

beforeEach(() => {
  resetCsrfToken();
  server.use(
    http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
    http.get("/api/auth/me", () =>
      HttpResponse.json({
        account: { id: "a1", email: fakeEmail("a", "b.example.test") },
        staff: { id: "s1", full_name: "Testa", roles: ["receptionist"] },
        organization: { id: "o1", name: "K", timezone: "Europe/Zagreb", currency: "EUR", locale: "hr" },
        clinics: [{ id: "c1", name: "Central Clinic" }],
        organization_clinics: [{ id: "c1", name: "Central Clinic" }, { id: "c2", name: "North Clinic" }],
        organizations_count: 1,
        totp_enrollment_required: false,
      }),
    ),
    http.get("/api/patients/:id/consents", () =>
      HttpResponse.json({ current: { marketing: "unknown" }, history: [] }),
    ),
    http.get("/api/patients/:id/enquiries", () => HttpResponse.json({ items: [], total: 0 })),
  );
});

describe("PatientDetailPage", () => {
  it("keeps the history pager available and retries a failed page", async () => {
    let secondPageAttempts = 0;
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(baseDetail)),
      http.get("/api/patients/p1/enquiries", ({ request }) => {
        const page = new URL(request.url).searchParams.get("page");
        if (page === "2" && ++secondPageAttempts === 1) {
          return HttpResponse.json({ error: "unexpected_error" }, { status: 500 });
        }
        return HttpResponse.json({
          items: [{
            id: `e${page}`, patient_id: "p1", lead_id: null, clinic_id: "c1", source: "phone",
            message: `Stranica ${page}`, received_at: "2026-01-01T10:00:00Z", preferred_contact_time: null,
          }],
          total: 26,
        });
      }),
    );
    renderRoutes(routes, "/patients/p1");
    await userEvent.click(await screen.findByRole("button", { name: "2" }));
    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(screen.getByRole("button", { name: "1" })).toBeEnabled();
    await userEvent.click(retry);
    expect(await screen.findByText("Stranica 2")).toBeInTheDocument();
    expect(secondPageAttempts).toBe(2);
  });

  it("shows enquiry history and refreshes it when logging an enquiry for an unassigned Clinic", async () => {
    const earlier: EnquiryOut = {
      id: "e1", patient_id: "p1", lead_id: "lead1", clinic_id: "c2", source: "phone",
      message: "Prije konverzije", received_at: "2026-01-01T10:00:00Z", preferred_contact_time: null,
      marketing_consent_requested: false,
    };
    const history = [earlier];
    let posted: unknown;
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(baseDetail)),
      http.get("/api/patients/p1/enquiries", () => HttpResponse.json({ items: history, total: history.length })),
      http.post("/api/patients/p1/enquiries", async ({ request }) => {
        posted = await request.json();
        const entry = { ...earlier, id: "e2", lead_id: null, message: "Novi upit" };
        history.unshift(entry);
        return HttpResponse.json(entry, { status: 201 });
      }),
    );
    renderRoutes(routes, "/patients/p1");
    expect(await screen.findByText("Prije konverzije")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Clinic"), "c2");
    await userEvent.type(screen.getByLabelText("Message"), "Novi upit");
    await userEvent.click(screen.getByRole("button", { name: "Log enquiry" }));
    expect(await screen.findByText("Novi upit")).toBeInTheDocument();
    expect(posted).toMatchObject({ clinic_id: "c2", message: "Novi upit" });
  });

  it("flags an Enquiry that requested marketing consent", async () => {
    const entry: EnquiryOut = {
      id: "e1", patient_id: "p1", lead_id: null, clinic_id: "c1", source: "website_form",
      message: "Bijeljenje zubi", received_at: "2026-01-01T10:00:00Z", preferred_contact_time: null,
      marketing_consent_requested: true,
    };
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(baseDetail)),
      http.get("/api/patients/p1/enquiries", () => HttpResponse.json({ items: [entry], total: 1 })),
    );
    renderRoutes(routes, "/patients/p1");
    expect(await screen.findByText("Requests marketing consent")).toBeInTheDocument();
  });

  it("reveals the OIB on demand", async () => {
    let reveals = 0;
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(baseDetail)),
      http.post("/api/patients/p1/reveal-oib", () => {
        reveals += 1;
        return HttpResponse.json({ oib: "11111111119" });
      }),
    );
    renderRoutes(routes, "/patients/p1");
    expect(await screen.findByText("*******1119")).toBeInTheDocument();
    expect(reveals).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: "Show OIB" }));
    expect(await screen.findByText("11111111119")).toBeInTheDocument();
    expect(reveals).toBe(1);
  });

  it("adds a contact guardian", async () => {
    let guardians: unknown[] = [];
    let posted: unknown = null;
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json({ ...baseDetail, is_minor: true, age: 9, guardians })),
      http.post("/api/patients/p1/guardians", async ({ request }) => {
        posted = await request.json();
        const g = {
          id: "l1",
          relationship: "parent",
          kind: "contact",
          guardian_id: "c9",
          display_name: "Testa Testač",
          phone: null,
          email: null,
        };
        guardians = [g];
        return HttpResponse.json(g, { status: 201 });
      }),
    );
    renderRoutes(routes, "/patients/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Add guardian" }));
    const dialog = await screen.findByRole("dialog", { name: "Add guardian" });
    await userEvent.click(within(dialog).getByText("New contact"));
    await userEvent.type(within(dialog).getByLabelText("Full name"), "Testa Testač");
    await userEvent.selectOptions(within(dialog).getByLabelText("Relationship"), "parent");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(posted).toEqual({ relationship: "parent", contact: { full_name: "Testa Testač" } }));
    expect(await screen.findByText("Testa Testač")).toBeInTheDocument();
  });

  it("requires a guardian when recording consent for a minor", async () => {
    let posted: unknown = null;
    const guardian = {
      id: "l1",
      relationship: "parent",
      kind: "patient",
      guardian_id: "p5",
      display_name: "Testpa Testić",
      phone: null,
      email: null,
    };
    server.use(
      http.get("/api/patients/p1", () =>
        HttpResponse.json({ ...baseDetail, is_minor: true, age: 9, guardians: [guardian] }),
      ),
      http.post("/api/patients/p1/consents", async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ id: "c1" }, { status: 201 });
      }),
    );
    renderRoutes(routes, "/patients/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Record consent" }));
    const dialog = await screen.findByRole("dialog", { name: "Record consent" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("Choose the guardian giving consent")).toBeInTheDocument();
    expect(posted).toBeNull();

    await userEvent.selectOptions(within(dialog).getByLabelText("Guardian giving consent"), "l1");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(posted).toEqual({
        purpose: "marketing",
        granted: true,
        source: "paper",
        given_by_guardian_link_id: "l1",
      }),
    );
  });

  it("redirects a merged patient to the kept record", async () => {
    server.use(
      http.get("/api/patients/p1", () =>
        HttpResponse.json({ error: "merged", merged_into: "p2" }, { status: 410 }),
      ),
      http.get("/api/patients/p2", () =>
        HttpResponse.json({ ...baseDetail, id: "p2", first_name: "Kept", last_name: "Record" }),
      ),
      http.get("/api/patients/p2/consents", () =>
        HttpResponse.json({ current: { marketing: "unknown" }, history: [] }),
      ),
    );
    renderRoutes({ "/patients/:id": <PatientDetailPage /> }, "/patients/p1");
    expect(await screen.findByRole("heading", { name: "Kept Record" })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/patients/p2");
    expect(screen.getByText(/was merged into this patient/)).toBeInTheDocument();
  });
  it("does not carry a revealed OIB over to another cached patient", async () => {
    const guardian = {
      id: "l1",
      relationship: "parent",
      kind: "patient",
      guardian_id: "p2",
      display_name: "Testpa Testić",
      phone: null,
      email: null,
    };
    let revealsB = 0;
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json({ ...baseDetail, guardians: [guardian] })),
      http.get("/api/patients/p2", () =>
        HttpResponse.json({ ...baseDetail, id: "p2", first_name: "Testpa", oib_masked: "*******9999" }),
      ),
      http.post("/api/patients/p1/reveal-oib", () => HttpResponse.json({ oib: "11111111119" })),
      http.post("/api/patients/p2/reveal-oib", () => {
        revealsB += 1;
        return HttpResponse.json({ oib: "11111111111" });
      }),
    );
    const { client } = renderRoutes(routes, "/patients/p1");
    client.setQueryData(["patient", "p2"], {
      ...baseDetail,
      id: "p2",
      first_name: "Testpa",
      oib_masked: "*******9999",
    });
    await userEvent.click(await screen.findByRole("button", { name: "Show OIB" }));
    expect(await screen.findByText("11111111119")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Testpa Testić" }));
    expect(await screen.findByText("*******9999")).toBeInTheDocument();
    expect(screen.queryByText("11111111119")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show OIB" })).toBeInTheDocument();
    expect(revealsB).toBe(0);
  });

  it("does not redirect a record that is merged into itself", async () => {
    server.use(
      http.get("/api/patients/p1", () =>
        HttpResponse.json({ error: "merged", merged_into: "p1" }, { status: 410 }),
      ),
    );
    renderRoutes(routes, "/patients/p1");
    expect(await screen.findByText("This record has been merged into another")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/patients/p1");
  });
  it("invalidates other cached patients when guardians change", async () => {
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(baseDetail)),
      http.post("/api/patients/p1/guardians", () =>
        HttpResponse.json(
          { id: "l1", relationship: "parent", kind: "contact", guardian_id: "c9", display_name: "Testa Testač", phone: null, email: null },
          { status: 201 },
        ),
      ),
    );
    const { client } = renderRoutes(routes, "/patients/p1");
    client.setQueryData(["patient", "p2"], { ...baseDetail, id: "p2" });
    await userEvent.click(await screen.findByRole("button", { name: "Add guardian" }));
    const dialog = await screen.findByRole("dialog", { name: "Add guardian" });
    await userEvent.click(within(dialog).getByText("New contact"));
    await userEvent.type(within(dialog).getByLabelText("Full name"), "Testa Testač");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(client.getQueryState(["patient", "p2"])?.isInvalidated).toBe(true));
  });
});
