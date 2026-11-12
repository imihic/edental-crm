import { fakeEmail } from "../../test/data";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Link } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Me } from "../../api/auth";
import { resetCsrfToken } from "../../api/client";
import type { components } from "../../api/schema";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import LeadDetailPage from "./LeadDetailPage";
import LeadsPage from "./LeadsPage";
import PatientDetailPage from "./PatientDetailPage";
import PatientsPage from "./PatientsPage";

type Lead = components["schemas"]["LeadDetail"];
type Patient = components["schemas"]["PatientDetail"];
const timestamp = "2026-11-10T12:00:00Z";
const lead: Lead = {
  id: "l1",
  full_name: "Testa Testma Testić",
  clinic_id: "c1",
  phone: "+12025550105",
  email: fakeEmail("testa", "hr.example.test"),
  stage: "new",
  lost_reason: null,
  lost_note: null,
  converted_patient_id: null,
  created_at: timestamp,
  updated_at: timestamp,
  consent: { marketing: "unknown" },
  enquiries: [{
    id: "e1", lead_id: "l1", patient_id: null, clinic_id: "c1",
    source: "phone", message: "Asked about a checkup", preferred_contact_time: null,
    received_at: timestamp, marketing_consent_requested: false,
  }],
  possible_duplicates: [
    { id: "p2", kind: "patient", display_name: "Testa Testač", reasons: ["email"] },
  ],
};
const patient: Patient = {
  id: "p1",
  first_name: "Testa",
  last_name: "Testić",
  phone: "+12025550105",
  email: fakeEmail("testa", "hr.example.test"),
  date_of_birth: null,
  oib_masked: null,
  address: null,
  notes: null,
  preferred_clinic: null,
  preferred_language: "hr",
  guardians: [],
  guardian_of: [],
  age: null,
  is_minor: false,
  consent: { marketing: "unknown" },
  created_at: timestamp,
  updated_at: timestamp,
};
const otherPatient: Patient = { ...patient, id: "p2", last_name: "Testač", phone: "+12025550107" };
const clinics = [{ id: "c1", name: "Central Clinic" }, { id: "c2", name: "West Clinic" }];
const me: Me = {
  account: { id: "a1", email: fakeEmail("staff", "hr.example.test") },
  staff: { id: "s1", full_name: "Staff", roles: ["receptionist"] },
  organization: { id: "o1", name: "Dental CRM", timezone: "Europe/Zagreb", currency: "EUR", locale: "hr" },
  clinics,
  organization_clinics: clinics,
  organizations_count: 1,
  totp_enrollment_required: false,
};
const routes = {
  "/leads": <LeadsPage />,
  "/leads/:id": <LeadDetailPage />,
  "/patients/:id": <PatientDetailPage />,
};

beforeEach(() => {
  resetCsrfToken();
  server.use(
    http.get("/api/auth/me", () => HttpResponse.json(me)),
    http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
    http.get("/api/leads/l1", () => HttpResponse.json(lead)),
    http.get("/api/leads/l2", () => HttpResponse.json({ ...lead, id: "l2", full_name: "Testan Testarić" })),
    http.get("/api/patients/p1", () => HttpResponse.json(patient)),
    http.get("/api/patients/p2", () => HttpResponse.json(otherPatient)),
    http.get("/api/patients/:id/consents", () => HttpResponse.json({ current: { marketing: "unknown" }, history: [] })),
    http.get("/api/patients/:id/enquiries", () => HttpResponse.json({ items: [], total: 0 })),
    http.get("/api/leads/:id/consents", () => HttpResponse.json({ current: { marketing: "unknown" }, history: [] })),
  );
});

describe("LeadsPage", () => {
  it("shows stage counts and filters by stage, clinic and search", async () => {
    const seen: URLSearchParams[] = [];
    server.use(http.get("/api/leads", ({ request }) => {
      const params = new URL(request.url).searchParams;
      seen.push(params);
      const contacted = { ...lead, id: "l2", full_name: "Testp Testarić", stage: "contacted" };
      const items = params.get("stage") === "contacted" ? [contacted] : [lead, contacted];
      return HttpResponse.json({
        items, total: items.length, counts: { new: 18, contacted: 9, consultation_booked: 2, converted: 7, lost: 5 },
      });
    }));
    renderRoutes(routes, "/leads");

    expect(await screen.findByRole("tab", { name: "New (18)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: lead.full_name })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Contacted (9)" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: lead.full_name })).not.toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "New (18)" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Testp Testarić" })).toHaveAttribute("href", "/leads/l2");
    await userEvent.selectOptions(screen.getByLabelText("Clinic"), "c2");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search leads" }), "Testp");
    await waitFor(() => expect(Object.fromEntries(seen.at(-1)!)).toMatchObject({
      stage: "contacted", clinic_id: "c2", q: "Testp", page: "1",
    }));
  });

  it("tells staff when a new enquiry attached to an existing patient", async () => {
    let body: unknown;
    server.use(
      http.get("/api/leads", () => HttpResponse.json({ items: [], total: 0, counts: {} })),
      http.post("/api/leads", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ attached_to: "patient", patient_id: "p1" }, { status: 201 });
      }),
    );
    renderRoutes(routes, "/leads");
    await userEvent.click(screen.getByRole("button", { name: "New lead" }));
    const dialog = await screen.findByRole("dialog", { name: "New lead" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Full name" }), "Testa Testić");
    await userEvent.type(within(dialog).getByLabelText("Email"), fakeEmail("testa", "hr.example.test"));
    await userEvent.selectOptions(within(dialog).getByLabelText("Source"), "email");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Clinic" }), "c2");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Message" }), "Can I book a checkup?");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("The enquiry was added to an existing patient.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open patient" })).toHaveAttribute("href", "/patients/p1");
    expect(screen.getByTestId("where")).toHaveTextContent("/leads");
    expect(body).toMatchObject({
      full_name: "Testa Testić", email: fakeEmail("testa", "hr.example.test"), source: "email", clinic_id: "c2",
      message: "Can I book a checkup?",
    });
  });
});

describe("LeadDetailPage", () => {
  it.each([
    ["new", ["contacted", "consultation_booked", "lost"]],
    ["contacted", ["consultation_booked", "lost"]],
    ["consultation_booked", ["contacted", "lost"]],
    ["lost", ["new"]],
    ["converted", []],
  ] as const)("only offers allowed moves from %s", async (stage, allowed) => {
    server.use(http.get("/api/leads/l1", () => HttpResponse.json({
      ...lead, stage, converted_patient_id: stage === "converted" ? "p1" : null,
    })));
    renderRoutes(routes, "/leads/l1");
    expect(await screen.findByRole("heading", { name: lead.full_name })).toBeInTheDocument();
    const selector = screen.queryByLabelText<HTMLSelectElement>("Change stage");
    if (allowed.length) {
      expect(Array.from(selector!.options, (option) => option.value).filter(Boolean)).toEqual(allowed);
      expect(screen.getByRole("button", { name: "Convert to patient" })).toBeInTheDocument();
    } else {
      expect(selector).toBeNull();
      expect(screen.queryByRole("button", { name: "Convert to patient" })).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Open patient" })).toHaveAttribute("href", "/patients/p1");
    }
  });

  it("requires a lost reason before changing the lead stage", async () => {
    let body: unknown;
    server.use(http.post("/api/leads/l1/stage", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ ...lead, stage: "lost", lost_reason: "price", lost_note: "Budget" });
    }));
    renderRoutes(routes, "/leads/l1");
    await userEvent.selectOptions(await screen.findByLabelText("Change stage"), "lost");
    const dialog = await screen.findByRole("dialog", { name: "Mark lead as lost" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(within(dialog).getByText("Choose a lost reason.")).toBeInTheDocument();
    expect(body).toBeUndefined();

    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Lost reason" }), "price");
    await userEvent.type(within(dialog).getByLabelText("Notes"), "Budget");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Budget")).toBeInTheDocument();
    expect(body).toEqual({ stage: "lost", lost_reason: "price", lost_note: "Budget" });
    expect(screen.getByRole("option", { name: "New" })).toBeInTheDocument();
  });

  it("shows enquiries and possible duplicates and records consent for a lead", async () => {
    const entry: components["schemas"]["ConsentOut"] = {
      id: "co1", purpose: "marketing", granted: true, source: "verbal",
      given_by_guardian_link_id: null, carried_from_consent_id: null,
      recorded_by_staff_member_id: "s1", recorded_at: timestamp,
    };
    let body: unknown;
    server.use(
      http.get("/api/leads/l1/consents", () => HttpResponse.json({
        current: { marketing: body ? "granted" : "unknown" }, history: body ? [entry] : [],
      })),
      http.post("/api/leads/l1/consents", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(entry, { status: 201 });
      }),
    );
    renderRoutes(routes, "/leads/l1");
    expect(await screen.findByText("Asked about a checkup")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Testa Testač" })).toHaveAttribute("href", "/patients/p2");
    await userEvent.click(screen.getByRole("button", { name: "Record consent" }));
    const dialog = await screen.findByRole("dialog", { name: "Record consent" });
    await userEvent.selectOptions(within(dialog).getByLabelText("Source"), "verbal");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Given", { exact: true })).toBeInTheDocument();
    expect(body).toEqual({ purpose: "marketing", granted: true, source: "verbal" });
  });

  it("converts a lead after duplicate confirmation and lands on the new patient", async () => {
    const bodies: Record<string, unknown>[] = [];
    const converted = { ...patient, first_name: "Testa Testma" };
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(converted)),
      http.post("/api/leads/l1/convert", async ({ request }) => {
        const body = await request.json() as Record<string, unknown>;
        bodies.push(body);
        if (!body.confirm_duplicates) {
          return HttpResponse.json(
            { error: "possible_duplicates", duplicates: lead.possible_duplicates }, { status: 409 },
          );
        }
        return HttpResponse.json(converted, { status: 201 });
      }),
    );
    renderRoutes(routes, "/leads/l1");
    await userEvent.click(await screen.findByRole("button", { name: "Convert to patient" }));
    const dialog = await screen.findByRole("dialog", { name: "Convert to patient" });
    expect(within(dialog).getByLabelText("First name")).toHaveValue("Testa Testma");
    expect(within(dialog).getByLabelText("Last name")).toHaveValue("Testić");
    expect(within(dialog).getByLabelText("Phone")).toHaveValue(lead.phone);
    expect(within(dialog).getByLabelText("Email")).toHaveValue(lead.email);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    const warning = await screen.findByRole("dialog", { name: "Possible duplicates" });
    expect(within(warning).getByRole("link", { name: "Testa Testač" })).toHaveAttribute("href", "/patients/p2");
    await userEvent.click(within(warning).getByRole("button", { name: "Convert anyway" }));

    expect(await screen.findByRole("heading", { name: lead.full_name })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/patients/p1");
    expect(bodies).toHaveLength(2);
    expect(bodies[0]).toMatchObject({ first_name: "Testa Testma", last_name: "Testić", email: lead.email });
    expect(bodies[0]).not.toHaveProperty("confirm_duplicates");
    expect(bodies[1]).toEqual({ ...bodies[0], confirm_duplicates: true });
  });

  it("discards the conversion dialog and its late navigation when switching leads", async () => {
    let respond!: () => void;
    const gate = new Promise<void>((resolve) => { respond = resolve; });
    let started = false;
    server.use(http.post("/api/leads/l1/convert", async () => {
      started = true;
      await gate;
      return HttpResponse.json(patient, { status: 201 });
    }));
    const { client } = renderRoutes({
      ...routes,
      "/leads/:id": <><Link to="/leads/l2">Next lead</Link><LeadDetailPage /></>,
    }, "/leads/l1");
    await userEvent.click(await screen.findByRole("button", { name: "Convert to patient" }));
    const dialog = await screen.findByRole("dialog", { name: "Convert to patient" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(started).toBe(true));
    await userEvent.click(screen.getByRole("link", { name: "Next lead" }));
    expect(await screen.findByRole("heading", { name: "Testan Testarić" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await act(async () => {
      respond();
      await vi.waitFor(() => expect(client.isMutating()).toBe(0));
    });
    expect(screen.getByTestId("where")).toHaveTextContent("/leads/l2");
  });
});

describe("Merge", () => {
  it("merges a patient choosing field values after explicit confirmation", async () => {
    let body: unknown;
    const kept = { ...patient, phone: otherPatient.phone };
    server.use(
      http.get("/api/patients", () => HttpResponse.json({ items: [patient, otherPatient], total: 2 })),
      http.get("/api/patients/p1", () => HttpResponse.json(body ? kept : patient)),
      http.get("/api/patients/p1/enquiries", () => HttpResponse.json(body ? {
        items: [{
          id: "e1", patient_id: "p1", lead_id: null, clinic_id: "c1", source: "phone",
          message: "Enquiry carried over by merge", received_at: "2026-01-01T10:00:00Z", preferred_contact_time: null,
        }],
        total: 1,
      } : { items: [], total: 0 })),
      http.post("/api/patients/p1/merge", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(kept);
      }),
    );
    renderRoutes(routes, "/patients/p1");
    expect(await screen.findByText("No enquiries")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Merge with…" }));
    const dialog = await screen.findByRole("dialog", { name: "Merge with…" });
    await userEvent.type(within(dialog).getByRole("searchbox", { name: "Search patients" }), "Testač");
    expect(within(dialog).queryByRole("button", { name: "Testa Testić" })).not.toBeInTheDocument();
    await userEvent.click(await within(dialog).findByRole("button", { name: "Testa Testač" }));
    await userEvent.click(await within(dialog).findByRole("radio", { name: "Phone from Testa Testač" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(body).toBeUndefined();
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm merge" }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await screen.findByText(otherPatient.phone!)).toBeInTheDocument();
    expect(await screen.findByText("Enquiry carried over by merge")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/patients/p1");
    expect(body).toEqual({
      retired_kind: "patient", retired_id: "p2", field_choices: { last_name: "kept", phone: "retired" },
    });
  });

  it("merges a lead into the selected patient using only lead contact fields", async () => {
    let body: unknown;
    server.use(
      http.get("/api/patients", () => HttpResponse.json({ items: [otherPatient], total: 1 })),
      http.post("/api/patients/p2/merge", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(otherPatient);
      }),
    );
    renderRoutes(routes, "/leads/l1");
    await userEvent.click(await screen.findByRole("button", { name: "Merge into patient…" }));
    const dialog = await screen.findByRole("dialog", { name: "Merge into patient…" });
    await userEvent.type(within(dialog).getByRole("searchbox", { name: "Search patients" }), "Testač");
    await userEvent.click(await within(dialog).findByRole("button", { name: "Testa Testač" }));
    expect(await within(dialog).findByRole("radio", { name: `Phone from ${lead.full_name}` })).toBeInTheDocument();
    expect(within(dialog).getAllByRole("radio")).toHaveLength(2);
    await userEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm merge" }));
    expect(await screen.findByRole("heading", { name: "Testa Testač" })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/patients/p2");
    expect(body).toEqual({ retired_kind: "lead", retired_id: "l1", field_choices: { phone: "kept" } });
  });
});

describe("Patient detail actions", () => {
  it("patches only changed fields so a concurrent edit survives", async () => {
    let current = patient;
    let body: Record<string, unknown> | undefined;
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(current)),
      http.patch("/api/patients/p1", async ({ request }) => {
        body = await request.json() as Record<string, unknown>;
        current = { ...current, ...body };
        return HttpResponse.json(current);
      }),
    );
    renderRoutes(routes, "/patients/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit" });
    current = { ...patient, email: fakeEmail("new", "hr.example.test") };
    await userEvent.type(within(dialog).getByLabelText("Notes"), "Call next week");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await screen.findByText(fakeEmail("new", "hr.example.test"))).toBeInTheDocument();
    expect(body).toEqual({ notes: "Call next week" });
  });

  it("remasks a revealed OIB after a detail update and keeps it out of the mutation cache", async () => {
    let current = { ...patient, oib_masked: "*******1119" };
    server.use(
      http.get("/api/patients/p1", () => HttpResponse.json(current)),
      http.post("/api/patients/p1/reveal-oib", () => HttpResponse.json({ oib: "11111111119" })),
    );
    const { client } = renderRoutes(routes, "/patients/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Show OIB" }));
    expect(await screen.findByText("11111111119")).toBeInTheDocument();
    const mutationData = client.getMutationCache().getAll().map((mutation) => mutation.state.data);
    expect(JSON.stringify(mutationData)).not.toContain("11111111119");

    current = { ...current, updated_at: "2026-11-11T12:00:00Z", oib_masked: "*******1234" };
    await act(() => client.invalidateQueries({ queryKey: ["patient", "p1"], exact: true }));
    expect(await screen.findByText("*******1234")).toBeInTheDocument();
    expect(screen.queryByText("11111111119")).not.toBeInTheDocument();
  });

  it.each(["Cancel", "Escape"])("stays on the patient list after dismissing a pending creation via %s", async (dismiss) => {
    let respond!: () => void;
    const gate = new Promise<void>((resolve) => { respond = resolve; });
    let started = false;
    server.use(
      http.get("/api/patients", () => HttpResponse.json({ items: [], total: 0 })),
      http.post("/api/patients", async () => {
        started = true;
        await gate;
        return HttpResponse.json(patient, { status: 201 });
      }),
    );
    const { client } = renderRoutes({ ...routes, "/patients": <PatientsPage /> }, "/patients");
    await userEvent.click(screen.getByRole("button", { name: "New patient" }));
    const dialog = await screen.findByRole("dialog", { name: "New patient" });
    await userEvent.type(within(dialog).getByLabelText("First name"), "Testa");
    await userEvent.type(within(dialog).getByLabelText("Last name"), "Testić");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(started).toBe(true));
    if (dismiss === "Cancel") {
      await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    } else {
      await userEvent.keyboard("{Escape}");
    }
    await act(async () => {
      respond();
      await vi.waitFor(() => expect(client.isMutating()).toBe(0));
    });
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(screen.getByTestId("where").textContent).toBe("/patients");
  });
});
