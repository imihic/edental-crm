import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { resetCsrfToken } from "../../api/client";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import PatientsPage from "./PatientsPage";

const summary = (id: string, first: string, last: string) => ({
  id,
  first_name: first,
  last_name: last,
  date_of_birth: "1990-05-01",
  phone: "+12025550105",
  email: null,
  oib_masked: "*******1119",
});

const routes = {
  "/patients": <PatientsPage />,
  "/patients/:id": <div>DETAIL PAGE</div>,
};

beforeEach(() => {
  resetCsrfToken();
  server.use(http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })));
});

describe("PatientsPage", () => {
  it("looks up an exact OIB without putting it in the URL or query cache", async () => {
    const oib = "11111111119";
    const requests: { url: string; body: unknown }[] = [];
    server.use(
      http.get("/api/patients", () => HttpResponse.json({ items: [], total: 0 })),
      http.post("/api/patients/lookup-oib", async ({ request }) => {
        requests.push({ url: request.url, body: await request.json() });
        return HttpResponse.json({ patient_id: requests.length === 1 ? null : "p1" });
      }),
    );
    const { client } = renderRoutes(routes, "/patients");
    await userEvent.click(screen.getByRole("button", { name: "Search by OIB" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Search by OIB" }));
    await userEvent.type(dialog.getByLabelText("OIB"), `${oib}0`);
    await userEvent.click(dialog.getByRole("button", { name: "Find patient" }));
    expect(await dialog.findByText("The OIB is not valid")).toBeInTheDocument();
    expect(requests).toHaveLength(0);
    await userEvent.clear(dialog.getByLabelText("OIB"));
    await userEvent.type(dialog.getByLabelText("OIB"), oib);
    await userEvent.click(dialog.getByRole("button", { name: "Find patient" }));
    expect(await dialog.findByText("No patient has that OIB")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/patients$/);

    await userEvent.click(dialog.getByRole("button", { name: "Find patient" }));
    expect(await screen.findByText("DETAIL PAGE")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/patients\/p1$/);
    expect(requests).toHaveLength(2);
    expect(requests.every((request) => !request.url.includes(oib))).toBe(true);
    expect(requests[0].body).toEqual({ oib });
    expect(JSON.stringify(client.getQueryCache().getAll().map((query) => query.queryKey))).not.toContain(oib);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });

  it("searches patients and shows results", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/patients", ({ request }) => {
        const url = new URL(request.url);
        const q = url.searchParams.get("q") ?? "";
        seen.push(q);
        const items = q
          ? [summary("p1", "Testm", "Testić")]
          : [summary("p1", "Testm", "Testić"), summary("p2", "Testan", "Testač")];
        return HttpResponse.json({ items, total: items.length });
      }),
    );
    renderRoutes(routes, "/patients");
    expect(await screen.findByText("Testan Testač")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("searchbox", { name: "Search patients" }), "testm");
    await waitFor(() => {
      expect(screen.getByText("Testm Testić")).toBeInTheDocument();
      expect(screen.queryByText("Testan Testač")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("where")).toHaveTextContent("/patients?q=testm");
    expect(seen).not.toContain("t");
    expect(seen).not.toContain("te");
  });

  it("shows the duplicate warning and creates anyway", async () => {
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.get("/api/patients", () => HttpResponse.json({ items: [], total: 0 })),
      http.post("/api/patients", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        if (!body.confirm_duplicates) {
          return HttpResponse.json(
            {
              error: "possible_duplicates",
              duplicates: [
                { kind: "patient", id: "p9", display_name: "Testan Testić", reasons: ["name_and_birth_date"] },
              ],
            },
            { status: 409 },
          );
        }
        return HttpResponse.json({ id: "p10" }, { status: 201 });
      }),
    );
    renderRoutes(routes, "/patients");
    await userEvent.click(await screen.findByRole("button", { name: "New patient" }));
    await userEvent.type(await screen.findByLabelText("First name"), "Testan");
    await userEvent.type(screen.getByLabelText("Last name"), "Testić");
    await userEvent.type(screen.getByLabelText("OIB"), "11111111110");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The OIB is not valid")).toBeInTheDocument();
    expect(bodies).toHaveLength(0);

    await userEvent.clear(screen.getByLabelText("OIB"));
    await userEvent.type(screen.getByLabelText("OIB"), "11111111119");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    const dialog = await screen.findByRole("dialog", { name: "Possible duplicates" });
    expect(dialog).toHaveTextContent("Testan Testić");
    expect(dialog).toHaveTextContent("Same name and date of birth");
    expect(screen.getByRole("link", { name: "Testan Testić" })).toHaveAttribute("href", "/patients/p9");

    await userEvent.click(screen.getByRole("button", { name: "Create anyway" }));
    expect(await screen.findByText("DETAIL PAGE")).toBeInTheDocument();
    expect(bodies).toHaveLength(2);
    expect(bodies[0].confirm_duplicates).toBeFalsy();
    expect(bodies[1]).toMatchObject({
      first_name: "Testan",
      last_name: "Testić",
      oib: "11111111119",
      preferred_language: "en",
      confirm_duplicates: true,
    });
  });
});
