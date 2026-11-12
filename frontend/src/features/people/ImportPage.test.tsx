import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { resetCsrfToken, setTenantSession } from "../../api/client";
import { renderRoutes } from "../../test/render";
import { server } from "../../test/server";
import ImportPage from "./ImportPage";

const counts = { total: 3, valid: 1, invalid: 1, duplicate: 1 };
const preview = {
  import_id: "i1",
  counts,
  ignored_columns: ["Unknown column"],
  rows: [
    { line: 2, status: "valid", errors: [], duplicates: [], in_file_duplicate_of_line: null },
    { line: 3, status: "invalid", errors: ["invalid_oib", "unknown_clinic"], duplicates: [], in_file_duplicate_of_line: null },
    {
      line: 4,
      status: "duplicate",
      errors: [],
      duplicates: [{ id: "p7", kind: "patient", display_name: "Testa Těstić", reasons: ["email"] }],
      in_file_duplicate_of_line: 2,
    },
  ],
};

const routes = { "/imports": <ImportPage /> };

beforeEach(() => {
  resetCsrfToken();
  server.use(
    http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
    http.get("/api/imports", () => HttpResponse.json({ items: [] })),
    http.post("/api/imports/patients/preview", () => HttpResponse.json(preview)),
  );
});

afterEach(() => setTenantSession(null, null));

async function previewFile(user: ReturnType<typeof userEvent.setup>) {
  const file = new File([Uint8Array.of(0xc6, 0xe6)], "patients.csv", { type: "text/csv" });
  await user.upload(screen.getByLabelText("CSV file"), file);
  await user.click(screen.getByRole("button", { name: "Preview import" }));
}

it("previews an import and commits it", async () => {
  const user = userEvent.setup();
  let uploaded: unknown;
  let committed: unknown;
  server.use(
    http.post("/api/imports/patients/preview", async ({ request }) => {
      uploaded = await request.json();
      return HttpResponse.json(preview);
    }),
    http.post("/api/imports/patients/i1/commit", async ({ request }) => {
      committed = await request.json();
      return HttpResponse.json({ created: 2, skipped: 1 });
    }),
    http.get("/api/imports", () =>
      HttpResponse.json({
        items: committed
          ? [{
              id: "i1",
              filename: "patients.csv",
              status: "committed",
              counts: { created: 2, skipped: 1 },
              created_at: "2026-11-10T09:00:00Z",
              committed_at: "2026-11-10T09:01:00Z",
            }]
          : [],
      }),
    ),
  );
  renderRoutes(routes, "/imports");

  await previewFile(user);
  expect(await screen.findByText("Total 3 · Valid 1 · Invalid 1 · Duplicates 1")).toBeVisible();
  expect(uploaded).toEqual({ filename: "patients.csv", content_base64: "xuY=" });
  expect(screen.getByRole("link", { name: "Testa Těstić" })).toHaveAttribute("href", "/patients/p7");
  expect(screen.getByText("Duplicate of line 2 in this file")).toBeVisible();
  expect(screen.getByText("Ignored columns: Unknown column")).toBeVisible();

  const include = screen.getByRole("checkbox", { name: "Include duplicates" });
  expect(include).not.toBeChecked();
  await user.click(include);
  await user.click(screen.getByRole("button", { name: "Confirm import" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Created 2 · Skipped 1");
  expect(committed).toEqual({ include_duplicates: true });
  const history = await screen.findByRole("table", { name: "Import history" });
  expect(within(history).getByText("patients.csv")).toBeVisible();
});

it("shows per-row error messages in English", async () => {
  const user = userEvent.setup();
  renderRoutes(routes, "/imports");
  await previewFile(user);

  const invalid = within(await screen.findByRole("row", { name: /3 Invalid/ }));
  expect(invalid.getByText("The OIB is not valid")).toBeVisible();
  expect(invalid.getByText("Clinic not found")).toBeVisible();
});

it("does not upload the CSV if the organization changes during the file read", async () => {
  const user = userEvent.setup();
  const readAsDataURL = FileReader.prototype.readAsDataURL;
  let finishRead: (() => void) | undefined;
  const read = vi.spyOn(FileReader.prototype, "readAsDataURL").mockImplementation(function (this: FileReader, file) {
    finishRead = () => readAsDataURL.call(this, file);
  });
  let uploadCount = 0;
  server.use(
    http.post("/api/imports/patients/preview", () => {
      uploadCount += 1;
      return HttpResponse.json(preview);
    }),
  );

  setTenantSession("org-a", "staff-a");
  renderRoutes(routes, "/imports");
  try {
    await previewFile(user);
    await waitFor(() => expect(finishRead).toBeDefined());
    setTenantSession("org-b", "staff-b");
    finishRead?.();
    await waitFor(() => expect(screen.getByRole("button", { name: "Preview import" })).toBeEnabled());
    expect(uploadCount).toBe(0);
  } finally {
    read.mockRestore();
  }
});
