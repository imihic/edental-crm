import { fakeEmail, fakePassword } from "../../test/data";
import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { errorKey, useChooseOrganization, useMe, useTenantSessionFence } from "../../api/auth";
import { ApiError, apiFetch, resetCsrfToken, setTenantSession, setTenantTransition } from "../../api/client";
import App from "../../App";
import "../../i18n";
import { server } from "../../test/server";

const ME = {
  account: { id: "a1", email: fakeEmail("testa", "clinic.example.test") },
  staff: { id: "s1", full_name: "Testa Testić", roles: ["receptionist", "dentist"] },
  organization: { id: "o1", name: "Example Dental", timezone: "Europe/Zagreb", currency: "EUR", locale: "hr" },
  clinics: [{ id: "c1", name: "Central Clinic" }],
  organizations_count: 1,
  totp_enrollment_required: false,
};

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  return { ...utils, client };
}

function backend(opts: {
  login?: unknown;
  loginStatus?: number;
  me?: Partial<typeof ME>;
  onLogoutRequest?: () => void;
  onLoginRequest?: () => void;
  totpFails?: boolean;
} = {}) {
  let signedIn = false;
  let me = { ...ME, ...opts.me };
  server.use(
    http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
    http.get("/api/auth/me", () =>
      signedIn ? HttpResponse.json(me) : HttpResponse.json({ error: "unauthenticated" }, { status: 401 }),
    ),
    http.post("/api/auth/login", () => {
      opts.onLoginRequest?.();
      if (opts.loginStatus && opts.loginStatus !== 200) {
        return HttpResponse.json({ error: "invalid_credentials" }, { status: opts.loginStatus });
      }
      const body = opts.login ?? { status: "ok" };
      if ((body as { status: string }).status === "ok") signedIn = true;
      return HttpResponse.json(body);
    }),
    http.post("/api/auth/totp", () => {
      if (opts.totpFails) return HttpResponse.json({ error: "invalid_code" }, { status: 401 });
      signedIn = true;
      return HttpResponse.json({ status: "ok" });
    }),
    http.post("/api/auth/organization", async ({ request }) => {
      const { organization_id } = (await request.json()) as { organization_id: string };
      me = {
        ...me,
        organization: { ...me.organization, id: organization_id, name: organization_id === "o2" ? "Sample Dental" : me.organization.name },
      };
      signedIn = true;
      return HttpResponse.json({ status: "ok" });
    }),
    http.post("/api/auth/logout", () => {
      signedIn = false;
      opts.onLogoutRequest?.();
      return new HttpResponse(null, { status: 204 });
    }),
  );
}

async function signIn(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText("Email"), fakeEmail("testa", "clinic.example.test"));
  await user.type(screen.getByLabelText("Password"), fakePassword());
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("auth flow", () => {
  beforeEach(() => {
    setTenantSession(null, null);
    setTenantTransition(null);
    resetCsrfToken();
  });

  it("fences the active organization until me has recovered from a cross-tab switch", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const nextMe = {
      ...ME,
      staff: { ...ME.staff, id: "s2" },
      organization: { ...ME.organization, id: "o2", name: "Sample Dental" },
    };
    let activeMe = ME;
    const expectedOrganizations: (string | null)[] = [];
    let finishRefresh!: () => void;
    const refresh = new Promise<void>((resolve) => {
      finishRefresh = resolve;
    });
    server.use(
      http.get("/api/auth/me", async () => {
        if (activeMe === nextMe) await refresh;
        return HttpResponse.json(activeMe);
      }),
      http.get("/api/patients", ({ request }) => {
        const expected = request.headers.get("X-Expected-Organization");
        expectedOrganizations.push(expected);
        return expected && expected !== activeMe.organization.id
          ? HttpResponse.json({ error: "organization_changed" }, { status: 409 })
          : HttpResponse.json({ items: [] });
      }),
    );
    function ProtectedView() {
      const { data: me } = useMe();
      const fenced = useTenantSessionFence(me);
      return <p>{fenced ? "Switching session" : me?.organization.name}</p>;
    }
    render(
      <QueryClientProvider client={client}>
        <ProtectedView />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Example Dental")).toBeInTheDocument();
    client.setQueryData(["patients"], ["old patient"]);
    activeMe = nextMe;

    try {
      await act(async () => {
        await expect(apiFetch("/api/patients")).rejects.toMatchObject({ code: "organization_changed" });
      });
      expect(await screen.findByText("Switching session")).toBeInTheDocument();
      expect(screen.queryByText("Example Dental")).toBeNull();
      expect(client.getQueryData(["patients"])).toBeUndefined();
    } finally {
      finishRefresh();
    }
    expect(await screen.findByText("Sample Dental")).toBeInTheDocument();
    await expect(apiFetch("/api/patients")).resolves.toEqual({ items: [] });
    expect(expectedOrganizations).toEqual(["o1", "o2"]);
  });

  it("fences the current view before the organization switch request completes", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    let activeMe = ME;
    let finishSwitch!: () => void;
    const switchRequest = new Promise<void>((resolve) => {
      finishSwitch = resolve;
    });
    server.use(
      http.get("/api/auth/me", () => HttpResponse.json(activeMe)),
      http.get("/api/auth/csrf", () => HttpResponse.json({ csrf_token: "t" })),
      http.post("/api/auth/organization", async () => {
        await switchRequest;
        activeMe = {
          ...ME,
          staff: { ...ME.staff, id: "s2" },
          organization: { ...ME.organization, id: "o2", name: "Sample Dental" },
        };
        return HttpResponse.json({ status: "ok" });
      }),
    );
    function ProtectedView() {
      const { data: me } = useMe();
      const fenced = useTenantSessionFence(me);
      const choose = useChooseOrganization();
      return fenced ? <p>Switching session</p> : (
        <button onClick={() => choose.mutate({ organization_id: "o2" })}>{me?.organization.name}</button>
      );
    }
    render(
      <QueryClientProvider client={client}>
        <ProtectedView />
      </QueryClientProvider>,
    );
    try {
      await userEvent.click(await screen.findByRole("button", { name: "Example Dental" }));
      expect(await screen.findByText("Switching session")).toBeInTheDocument();
      expect(screen.queryByText("Example Dental")).toBeNull();
    } finally {
      finishSwitch();
    }
    expect(await screen.findByRole("button", { name: "Sample Dental" })).toBeInTheDocument();
  });

  it("signs in and shows the shell with organization name", async () => {
    backend();
    renderApp();
    await signIn(userEvent.setup());
    expect(await screen.findByText("Example Dental")).toBeInTheDocument();
    expect(screen.getByText(/Testa Testić/)).toBeInTheDocument();
    expect(screen.getByText(/Receptionist, Dentist/)).toBeInTheDocument();
    expect(screen.getByText("Central Clinic")).toBeInTheDocument();
  });

  it("shows the English invalid-credentials message on 401", async () => {
    backend({ loginStatus: 401 });
    renderApp();
    await signIn(userEvent.setup());
    expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
  });

  it("validates the email before calling the API", async () => {
    let loginCalls = 0;
    backend({ onLoginRequest: () => loginCalls++ });
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "invalid-email");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(loginCalls).toBe(0);
  });

  it("shows the English invalid-code message on a wrong TOTP code", async () => {
    backend({ login: { status: "totp_required" }, totpFails: true });
    renderApp();
    const user = userEvent.setup();
    await signIn(user);
    await user.type(await screen.findByLabelText("Code"), "000000");
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Invalid code")).toBeInTheDocument();
  });

  it("shows an error with retry when /me fails with a non-401 error", async () => {
    let fail = true;
    server.use(
      http.get("/api/auth/me", () =>
        fail
          ? HttpResponse.json({ error: "internal" }, { status: 500 })
          : HttpResponse.json({ error: "unauthenticated" }, { status: 401 }),
      ),
    );
    renderApp();
    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
    fail = false;
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("drops cached non-me queries when switching organization", async () => {
    backend({ me: { organizations_count: 2 } });
    server.use(
      http.get("/api/auth/organizations", () =>
        HttpResponse.json({ organizations: [{ id: "o1", name: "Example Dental" }, { id: "o2", name: "Sample Dental" }] }),
      ),
    );
    const { client } = renderApp();
    const user = userEvent.setup();
    await signIn(user);
    const select = await screen.findByLabelText("Switch organization");
    await screen.findByRole("option", { name: "Sample Dental" });
    client.setQueryData(["patients"], [{ id: "p1" }]);
    await user.selectOptions(select, "o2");
    await screen.findByText("Sample Dental", { selector: "p" });
    expect(client.getQueryData(["patients"])).toBeUndefined();
    expect(await screen.findByRole("option", { name: "Sample Dental" })).toBeInTheDocument();
  });

  it("asks for a code when totp_required, then signs in", async () => {
    backend({ login: { status: "totp_required" } });
    renderApp();
    const user = userEvent.setup();
    await signIn(user);
    await user.type(await screen.findByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Example Dental")).toBeInTheDocument();
  });

  it("lets a multi-organization account choose, then shows the chosen organization", async () => {
    backend({
      login: { status: "choose_organization", organizations: [{ id: "o1", name: "Example Dental" }, { id: "o2", name: "Sample Dental" }] },
      me: { organizations_count: 2 },
    });
    renderApp();
    const user = userEvent.setup();
    await signIn(user);
    await user.click(await screen.findByRole("button", { name: "Sample Dental" }));
    expect(await screen.findByText("Sample Dental", { selector: "p" })).toBeInTheDocument();
  });

  it("shows the organization switcher only when organizations_count > 1", async () => {
    backend({ login: { status: "ok" } });
    server.use(http.get("/api/auth/organizations", () => HttpResponse.json({ organizations: [{ id: "o1", name: "Example Dental" }] })));
    const { unmount } = renderApp();
    await signIn(userEvent.setup());
    await screen.findByText("Example Dental");
    expect(screen.queryByLabelText("Switch organization")).not.toBeInTheDocument();
    unmount();

    resetCsrfToken();
    backend({ me: { organizations_count: 2 } });
    server.use(
      http.get("/api/auth/organizations", () =>
        HttpResponse.json({ organizations: [{ id: "o1", name: "Example Dental" }, { id: "o2", name: "Sample Dental" }] }),
      ),
    );
    renderApp();
    const user = userEvent.setup();
    await signIn(user);
    const select = await screen.findByLabelText("Switch organization");
    await screen.findByRole("option", { name: "Sample Dental" });
    await user.selectOptions(select, "o2");
    expect(await screen.findByText("Sample Dental", { selector: "p" })).toBeInTheDocument();
  });

  it("sends a fenced manager to TOTP enrollment", async () => {
    backend({ me: { totp_enrollment_required: true, staff: { ...ME.staff, roles: ["clinic_manager"] } } });
    server.use(
      http.post("/api/auth/totp/enroll", () => HttpResponse.json({ otpauth_uri: "otpauth://totp/Dental:testa?secret=ABC" })),
    );
    renderApp();
    await signIn(userEvent.setup());
    expect(await screen.findByText("Set up two-step verification")).toBeInTheDocument();
    expect(await screen.findByRole("img")).toBeInTheDocument();
    expect(screen.getByLabelText("Code")).toBeInTheDocument();
  });

  it("logs out and returns to the login page", async () => {
    let loggedOut = false;
    backend({ onLogoutRequest: () => (loggedOut = true) });
    renderApp();
    const user = userEvent.setup();
    await signIn(user);
    await user.click(await screen.findByRole("button", { name: "Log out" }));
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(loggedOut).toBe(true);
  });

  it("lets a fenced manager log out from the enrollment page", async () => {
    let loggedOut = false;
    backend({
      me: { totp_enrollment_required: true, staff: { ...ME.staff, roles: ["clinic_manager"] } },
      onLogoutRequest: () => (loggedOut = true),
    });
    server.use(
      http.post("/api/auth/totp/enroll", () => HttpResponse.json({ otpauth_uri: "otpauth://totp/Dental:testa?secret=ABC" })),
    );
    renderApp();
    const user = userEvent.setup();
    await signIn(user);
    await screen.findByText("Set up two-step verification");
    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(loggedOut).toBe(true);
  });

  it("offers the organization switcher on the enrollment page for several organizations", async () => {
    backend({
      me: { organizations_count: 2, totp_enrollment_required: true, staff: { ...ME.staff, roles: ["clinic_manager"] } },
    });
    server.use(
      http.post("/api/auth/totp/enroll", () => HttpResponse.json({ otpauth_uri: "otpauth://totp/Dental:testa?secret=ABC" })),
      http.get("/api/auth/organizations", () =>
        HttpResponse.json({ organizations: [{ id: "o1", name: "Example Dental" }, { id: "o2", name: "Sample Dental" }] }),
      ),
    );
    renderApp();
    await signIn(userEvent.setup());
    await screen.findByText("Set up two-step verification");
    expect(await screen.findByLabelText("Switch organization")).toBeInTheDocument();
  });

  it("labels the QR code and shows the secret for manual entry, grouped in fours", async () => {
    backend({ me: { totp_enrollment_required: true, staff: { ...ME.staff, roles: ["clinic_manager"] } } });
    server.use(
      http.post("/api/auth/totp/enroll", () =>
        HttpResponse.json({ otpauth_uri: `otpauth://totp/Dental%20CRM:testa%40clinic.example.test?secret=${"TEST".repeat(4)}&issuer=Dental%20CRM` }),
      ),
    );
    renderApp();
    await signIn(userEvent.setup());
    expect(await screen.findByRole("img", { name: "QR code for setting up two-step verification" })).toBeInTheDocument();
    expect(screen.getByText("TEST TEST TEST TEST")).toBeInTheDocument();
  });

  it("shows translated messages for totp_already_enabled and json_required", async () => {
    backend({ me: { totp_enrollment_required: true, staff: { ...ME.staff, roles: ["clinic_manager"] } } });
    server.use(
      http.post("/api/auth/totp/enroll", () => HttpResponse.json({ error: "totp_already_enabled" }, { status: 409 })),
    );
    renderApp();
    await signIn(userEvent.setup());
    expect(await screen.findByText("Two-step verification is already enabled")).toBeInTheDocument();
    expect(errorKey(new ApiError(415, "json_required"))).toBe("auth.errors.json_required");
  });
});
