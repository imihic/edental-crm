import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useSyncExternalStore } from "react";
import {
  ApiError,
  apiFetch,
  getTenantSession,
  resetCsrfToken,
  setTenantSession,
  setTenantTransition,
  subscribeTenantSession,
} from "./client";
import type { components, paths } from "./schema";

type Schemas = components["schemas"];
type JsonBody<T> = T extends { requestBody: { content: { "application/json": infer B } } } ? B : never;

export type Me = Schemas["MeResponse"];
export type LoginResult = Schemas["LoginResponse"];
export type OrganizationOut = Schemas["OrganizationOut"];
export type OrganizationsResult = Schemas["OrganizationsResponse"];
export type LoginBody = JsonBody<paths["/api/auth/login"]["post"]>;
export type TotpBody = JsonBody<paths["/api/auth/totp"]["post"]>;
export type ChooseOrganizationBody = JsonBody<paths["/api/auth/organization"]["post"]>;
export type ConfirmBody = JsonBody<paths["/api/auth/totp/confirm"]["post"]>;

const KNOWN_ERRORS = [
  "invalid_credentials",
  "invalid_code",
  "forbidden",
  "totp_enrollment_required",
  "unauthenticated",
  "validation_error",
  "network_error",
  "invalid_response",
  "csrf_failed",
  "totp_already_enabled",
  "json_required",
];

export function errorKey(error: unknown): string {
  const code = error instanceof ApiError ? error.code : "";
  return KNOWN_ERRORS.includes(code) ? `auth.errors.${code}` : "auth.errors.unknown";
}

const ME_QUERY_KEY = ["me"] as const;
const ORGANIZATIONS_QUERY_KEY = ["organizations"] as const;
const SESSION_MUTATION_KEY = ["session"] as const;

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ME_QUERY_KEY,
    queryFn: async ({ signal }) => {
      try {
        return await apiFetch<Me>("/api/auth/me", { signal });
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: "always",
  });
}

export function useOrganizations(enabled = true) {
  return useQuery<OrganizationsResult>({
    queryKey: ORGANIZATIONS_QUERY_KEY,
    queryFn: () => apiFetch<OrganizationsResult>("/api/auth/organizations"),
    enabled,
    retry: false,
  });
}

function clearTenantData(qc: QueryClient) {
  qc.removeQueries({
    predicate: ({ queryKey: [key] }) => key !== ME_QUERY_KEY[0] && key !== ORGANIZATIONS_QUERY_KEY[0],
  });
  const mutations = qc.getMutationCache();
  for (const mutation of mutations.getAll()) {
    if (mutation.options.mutationKey?.[0] !== SESSION_MUTATION_KEY[0] || mutation.state.status !== "pending") {
      mutations.remove(mutation);
    }
  }
}

async function refreshTenantSession(qc: QueryClient) {
  const previousAccount = qc.getQueryData<Me | null>(ME_QUERY_KEY)?.account.id;
  await qc.cancelQueries();
  clearTenantData(qc);
  await qc.invalidateQueries({ queryKey: ME_QUERY_KEY });
  const refreshed = qc.getQueryState<Me | null>(ME_QUERY_KEY);
  const me = refreshed?.status === "success" ? refreshed.data : null;
  if (!me || me.account.id !== previousAccount) qc.removeQueries({ queryKey: ORGANIZATIONS_QUERY_KEY });
  setTenantSession(me?.organization.id ?? null, me?.staff.id ?? null);
}

export function useTenantSessionFence(me: Me | null | undefined): boolean {
  const qc = useQueryClient();
  const session = useSyncExternalStore(subscribeTenantSession, getTenantSession);
  const recovering = useRef(false);
  const organizationId = me?.organization.id ?? null;
  const staffId = me?.staff.id ?? null;
  const identityChanged = session.organizationId !== organizationId || session.staffId !== staffId;

  useLayoutEffect(() => {
    if (me === undefined || session.transition !== null || !identityChanged) return;
    const state = qc.getQueryState<Me | null>(ME_QUERY_KEY);
    if (state?.status !== "success") return;
    const current = state.data;
    if ((current?.organization.id ?? null) !== organizationId || (current?.staff.id ?? null) !== staffId) return;
    clearTenantData(qc);
    qc.removeQueries({ queryKey: ORGANIZATIONS_QUERY_KEY });
    setTenantSession(organizationId, staffId);
  }, [identityChanged, me, organizationId, qc, session.transition, staffId]);

  useEffect(() => {
    if (session.transition !== "mismatch" || recovering.current) return;
    recovering.current = true;
    void refreshTenantSession(qc).finally(() => {
      recovering.current = false;
      setTenantTransition(null);
    });
  }, [qc, session.transition]);

  return session.transition !== null || identityChanged;
}

function useSessionMutation<V, R>(fn: (v: V) => Promise<R>, changesTenant = false) {
  const qc = useQueryClient();
  return useMutation<R, ApiError, V>({
    mutationKey: SESSION_MUTATION_KEY,
    mutationFn: fn,
    onMutate: changesTenant ? () => {
      setTenantTransition("switching");
      return qc.cancelQueries();
    } : undefined,
    onSuccess: changesTenant ? undefined : async () => {
      resetCsrfToken();
      await qc.invalidateQueries({ queryKey: ME_QUERY_KEY });
    },
    onSettled: changesTenant ? async () => {
      try {
        await refreshTenantSession(qc);
      } finally {
        setTenantTransition(null);
      }
    } : undefined,
  });
}

export const useLogin = () =>
  useSessionMutation((body: LoginBody) =>
    apiFetch<LoginResult>("/api/auth/login", { method: "POST", body }),
  );

export const useVerifyTotp = () =>
  useSessionMutation((body: TotpBody) =>
    apiFetch<LoginResult>("/api/auth/totp", { method: "POST", body }),
  );

export const useChooseOrganization = () =>
  useSessionMutation((body: ChooseOrganizationBody) =>
    apiFetch<Schemas["OkResponse"]>("/api/auth/organization", { method: "POST", body }),
    true,
  );

export const useEnrollTotp = () =>
  useSessionMutation(() =>
    apiFetch<Schemas["EnrollResponse"]>("/api/auth/totp/enroll", { method: "POST" }),
  );

export const useConfirmTotp = () =>
  useSessionMutation((body: ConfirmBody) =>
    apiFetch<Schemas["OkResponse"]>("/api/auth/totp/confirm", { method: "POST", body }),
  );

export const useLogout = () =>
  useSessionMutation(() => apiFetch<void>("/api/auth/logout", { method: "POST" }), true);
