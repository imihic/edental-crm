import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "../test/server";
import { ApiError, apiFetch, resetCsrfToken, setTenantSession, setTenantTransition } from "./client";

describe("apiFetch", () => {
  beforeEach(() => {
    setTenantSession(null, null);
    setTenantTransition(null);
    resetCsrfToken();
  });

  it("fetches csrf once and sends it on POST", async () => {
    let csrfCalls = 0;
    const seen: (string | null)[] = [];
    server.use(
      http.get("/api/auth/csrf", () => {
        csrfCalls += 1;
        return HttpResponse.json({ csrf_token: "tok1" });
      }),
      http.post("/api/auth/login", ({ request }) => {
        seen.push(request.headers.get("X-CSRF-Token"));
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiFetch("/api/auth/login", { method: "POST", body: { a: 1 } });
    await apiFetch("/api/auth/login", { method: "POST", body: { a: 2 } });
    expect(csrfCalls).toBe(1);
    expect(seen).toEqual(["tok1", "tok1"]);
  });

  it("does not fetch csrf or send the header on GET", async () => {
    let header: string | null = "unset";
    server.use(
      http.get("/api/auth/me", ({ request }) => {
        header = request.headers.get("X-CSRF-Token");
        return HttpResponse.json({ id: 1 });
      }),
    );
    await apiFetch("/api/auth/me");
    expect(header).toBeNull();
  });

  it("submits a public enquiry without consulting the staff session", async () => {
    setTenantSession("org-a", "staff-a");
    let csrfCalls = 0;
    let enquiryRequest: Request | undefined;
    server.use(
      http.get("/api/auth/csrf", () => {
        csrfCalls += 1;
        return HttpResponse.json({ error: "internal_error" }, { status: 500 });
      }),
      http.post("/api/public/enquiry-forms/example/enquiries", ({ request }) => {
        enquiryRequest = request;
        return HttpResponse.json({ status: "received" }, { status: 201 });
      }),
    );

    const fetchSpy = vi.spyOn(globalThis, "fetch");
    try {
      await apiFetch("/api/public/enquiry-forms/example/enquiries", { method: "POST", body: {} });
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/public/enquiry-forms/example/enquiries",
        expect.objectContaining({ credentials: "omit", referrerPolicy: "no-referrer" }),
      );
    } finally {
      fetchSpy.mockRestore();
    }

    expect(csrfCalls).toBe(0);
    expect(enquiryRequest?.headers.get("X-CSRF-Token")).toBeNull();
    expect(enquiryRequest?.headers.get("X-Expected-Organization")).toBeNull();
    expect(enquiryRequest?.headers.get("Content-Type")).toBe("application/json");
  });

  it("refetches csrf and retries once on 403 csrf_failed", async () => {
    let csrfCalls = 0;
    let postCalls = 0;
    server.use(
      http.get("/api/auth/csrf", () => {
        csrfCalls += 1;
        return HttpResponse.json({ csrf_token: `tok${csrfCalls}` });
      }),
      http.post("/api/auth/logout", ({ request }) => {
        postCalls += 1;
        if (request.headers.get("X-CSRF-Token") === "tok1") {
          return HttpResponse.json({ error: "csrf_failed" }, { status: 403 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await expect(apiFetch("/api/auth/logout", { method: "POST" })).resolves.toBeUndefined();
    expect(csrfCalls).toBe(2);
    expect(postCalls).toBe(2);
  });

  it("retries at most once", async () => {
    let postCalls = 0;
    server.use(
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
      http.post("/api/auth/logout", () => {
        postCalls += 1;
        return HttpResponse.json({ error: "csrf_failed" }, { status: 403 });
      }),
    );
    await expect(apiFetch("/api/auth/logout", { method: "POST" })).rejects.toMatchObject({
      status: 403,
      code: "csrf_failed",
    });
    expect(postCalls).toBe(2);
  });

  it("pins a patient create to the original organization across a CSRF retry", async () => {
    setTenantSession("org-a", "staff-a");
    let cookieOrganization = "org-a";
    const attempts: [string | null, string | null][] = [];
    server.use(
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: cookieOrganization })),
      http.post("/api/patients", ({ request }) => {
        const token = request.headers.get("X-CSRF-Token");
        const expected = request.headers.get("X-Expected-Organization");
        attempts.push([token, expected]);
        if (attempts.length === 1) {
          cookieOrganization = "org-b";
          return HttpResponse.json({ error: "csrf_failed" }, { status: 403 });
        }
        if (expected && expected !== cookieOrganization) {
          return HttpResponse.json({ error: "organization_changed" }, { status: 409 });
        }
        return HttpResponse.json({ id: "created-in-org-b" }, { status: 201 });
      }),
    );

    await expect(apiFetch("/api/patients", { method: "POST", body: { first_name: "Testa" } }))
      .rejects.toMatchObject({ status: 409, code: "organization_changed" });
    expect(attempts).toEqual([["org-a", "org-a"], ["org-b", "org-a"]]);
  });

  it("discards a tenant mutation response after a local switch starts", async () => {
    setTenantSession("org-a", "staff-a");
    server.use(
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
      http.post("/api/patients", () => {
        setTenantTransition("switching");
        return HttpResponse.json({ id: "late-patient" }, { status: 201 });
      }),
    );

    await expect(apiFetch("/api/patients", { method: "POST", body: {} }))
      .rejects.toMatchObject({ code: "organization_changed" });
  });

  it("throws ApiError with the server code", async () => {
    server.use(
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
      http.post("/api/auth/login", () =>
        HttpResponse.json({ error: "invalid_credentials" }, { status: 401 }),
      ),
    );
    const err = (await apiFetch<never>("/api/auth/login", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.code).toBe("invalid_credentials");
  });

  it("carries validation fields on 422", async () => {
    server.use(
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
      http.post("/api/auth/login", () =>
        HttpResponse.json({ error: "validation_error", fields: ["email"] }, { status: 422 }),
      ),
    );
    const err = (await apiFetch<never>("/api/auth/login", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err.fields).toEqual(["email"]);
  });

  it("returns undefined on 204", async () => {
    server.use(
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
      http.post("/api/auth/logout", () => new HttpResponse(null, { status: 204 })),
    );
    await expect(apiFetch("/api/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("sends Content-Type json on a bodiless POST", async () => {
    let ct: string | null = null;
    server.use(
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
      http.post("/api/auth/logout", ({ request }) => {
        ct = request.headers.get("Content-Type");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await apiFetch("/api/auth/logout", { method: "POST" });
    expect(ct).toBe("application/json");
  });

  it("fetches csrf once for concurrent first POSTs", async () => {
    let csrfCalls = 0;
    server.use(
      http.get("/api/auth/csrf", async () => {
        csrfCalls += 1;
        await new Promise((r) => setTimeout(r, 20));
        return HttpResponse.json({ csrf_token: "t" });
      }),
      http.post("/api/x", () => new HttpResponse(null, { status: 204 })),
    );
    await Promise.all([
      apiFetch("/api/x", { method: "POST" }),
      apiFetch("/api/x", { method: "POST" }),
    ]);
    expect(csrfCalls).toBe(1);
  });

  it("maps network failures to ApiError network_error", async () => {
    server.use(http.get("/api/auth/me", () => HttpResponse.error()));
    await expect(apiFetch("/api/auth/me")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });

  it("maps a non-JSON 2xx body to invalid_response", async () => {
    server.use(http.get("/api/auth/me", () => new HttpResponse("<html>", { status: 200 })));
    await expect(apiFetch("/api/auth/me")).rejects.toMatchObject({
      status: 200,
      code: "invalid_response",
    });
  });
});

describe("ApiError body", () => {
  it("keeps the parsed error body (duplicates, merged_into)", async () => {
    server.use(
      http.get("/api/x", () =>
        HttpResponse.json({ error: "merged", merged_into: "p2" }, { status: 410 }),
      ),
    );
    const err = await apiFetch("/api/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(410);
    expect((err as ApiError).body).toEqual({ error: "merged", merged_into: "p2" });
  });

  it("has an undefined body for a non-JSON error", async () => {
    server.use(http.get("/api/x", () => new HttpResponse("boom", { status: 500 })));
    const err = (await apiFetch("/api/x").catch((e: unknown) => e)) as ApiError;
    expect(err.body).toBeUndefined();
  });
});
