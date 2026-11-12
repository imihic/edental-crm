export class ApiError extends Error {
  status: number;
  code: string;
  fields?: string[];
  body?: unknown;

  constructor(status: number, code: string, fields?: string[], body?: unknown) {
    super(code);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    if (fields) this.fields = fields;
    if (body !== undefined) this.body = body;
  }
}

let csrfPromise: Promise<string> | null = null;

type TenantTransition = "switching" | "mismatch" | null;
type TenantSession = {
  organizationId: string | null;
  staffId: string | null;
  transition: TenantTransition;
};

let tenantSession: TenantSession = { organizationId: null, staffId: null, transition: null };
let tenantRequests = new AbortController();
const tenantListeners = new Set<() => void>();

export function getTenantSession(): TenantSession {
  return tenantSession;
}

export function subscribeTenantSession(listener: () => void): () => void {
  tenantListeners.add(listener);
  return () => tenantListeners.delete(listener);
}

function updateTenantSession(next: TenantSession) {
  const previousRequests = tenantRequests;
  tenantSession = next;
  tenantRequests = new AbortController();
  resetCsrfToken();
  previousRequests.abort(new ApiError(409, "organization_changed"));
  for (const listener of tenantListeners) listener();
}

export function setTenantSession(organizationId: string | null, staffId: string | null): void {
  if (tenantSession.organizationId === organizationId && tenantSession.staffId === staffId) return;
  updateTenantSession({ ...tenantSession, organizationId, staffId });
}

export function setTenantTransition(transition: TenantTransition): void {
  if (tenantSession.transition === transition) return;
  updateTenantSession({ ...tenantSession, transition });
}

export function resetCsrfToken(): void {
  csrfPromise = null;
}

function getCsrfToken(): Promise<string> {
  if (csrfPromise === null) {
    const p = (async () => {
      const res = await rawFetch("/api/auth/csrf", { credentials: "same-origin" });
      if (!res.ok) throw new ApiError(res.status, "csrf_unavailable");
      const data = (await res.json().catch(() => null)) as { csrf_token?: string } | null;
      if (!data || typeof data.csrf_token !== "string") {
        throw new ApiError(res.status, "invalid_response");
      }
      return data.csrf_token;
    })();
    csrfPromise = p;
    p.catch(() => {
      if (csrfPromise === p) csrfPromise = null;
    });
  }
  return csrfPromise;
}

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch {
    init.signal?.throwIfAborted();
    throw new ApiError(0, "network_error");
  }
}

type RequestContext = {
  publicRequest: boolean;
  organizationId: string | null;
  signal?: AbortSignal;
};

async function send(
  path: string,
  method: string,
  body: unknown,
  { publicRequest, organizationId, signal }: RequestContext,
): Promise<{ res: Response; used: Promise<string> | null }> {
  const headers: Record<string, string> = {};
  if (organizationId !== null) headers["X-Expected-Organization"] = organizationId;
  let used: Promise<string> | null = null;
  const mutation = method !== "GET" && method !== "HEAD";
  if (mutation || body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (mutation && !publicRequest) {
    used = getCsrfToken();
    headers["X-CSRF-Token"] = await used;
  }
  signal?.throwIfAborted();
  const res = await rawFetch(path, {
    method,
    headers,
    credentials: publicRequest ? "omit" : "same-origin",
    referrerPolicy: publicRequest ? "no-referrer" : undefined,
    signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { res, used };
}

async function errorFrom(res: Response): Promise<ApiError> {
  let data: { error?: string; fields?: string[] } = {};
  let body: unknown;
  try {
    body = await res.json();
    if (body && typeof body === "object") data = body as typeof data;
  } catch {
  }
  return new ApiError(res.status, data.error ?? "unknown", data.fields, body);
}

export async function apiFetch<T>(
  path: string,
  init: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const publicRequest = path.startsWith("/api/public/");
  const tenantRequest = path.startsWith("/api/") && !publicRequest
    && !path.startsWith("/api/auth/") && path.split("?")[0] !== "/api/health";
  if (tenantRequest && tenantSession.transition !== null) {
    throw new ApiError(409, "organization_changed");
  }
  const tenantSignal = tenantRequest ? tenantRequests.signal : undefined;
  const signal = init.signal && tenantSignal ? AbortSignal.any([init.signal, tenantSignal]) : init.signal ?? tenantSignal;
  const organizationId = tenantRequest ? tenantSession.organizationId : null;
  const context = { publicRequest, organizationId, signal };
  signal?.throwIfAborted();
  let { res, used } = await send(path, method, init.body, context);
  signal?.throwIfAborted();

  if (!res.ok) {
    let err = await errorFrom(res);
    signal?.throwIfAborted();
    if (err.status === 403 && err.code === "csrf_failed" && used !== null) {
      if (csrfPromise === used) csrfPromise = null;
      ({ res } = await send(path, method, init.body, context));
      signal?.throwIfAborted();
      if (!res.ok) err = await errorFrom(res);
    }
    if (!res.ok) {
      signal?.throwIfAborted();
      if (organizationId !== null && err.status === 409 && err.code === "organization_changed") {
        setTenantTransition("mismatch");
      }
      throw err;
    }
  }
  if (res.status === 204) return undefined as T;
  try {
    const data = (await res.json()) as T;
    signal?.throwIfAborted();
    return data;
  } catch {
    signal?.throwIfAborted();
    throw new ApiError(res.status, "invalid_response");
  }
}
