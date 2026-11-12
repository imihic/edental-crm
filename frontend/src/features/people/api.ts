import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "../../api/client";
import type { components, paths } from "../../api/schema";

type Schemas = components["schemas"];
type PatientListOperation = paths["/api/patients"]["get"];
type PatientDetailOperation = paths["/api/patients/{patient_id}"]["get"];
type PatientEnquiryHistoryOperation = paths["/api/patients/{patient_id}/enquiries"]["get"];
type PatientOibLookupOperation = paths["/api/patients/lookup-oib"]["post"];
type PatientEnquiryHistory = PatientEnquiryHistoryOperation["responses"][200]["content"]["application/json"];
type PatientOibLookupResult = PatientOibLookupOperation["responses"][200]["content"]["application/json"];

export type PatientDetail = PatientDetailOperation["responses"][200]["content"]["application/json"];
export type PatientSummary = Schemas["PatientSummary"];
export type PatientList = PatientListOperation["responses"][200]["content"]["application/json"];
export type PatientCreate = paths["/api/patients"]["post"]["requestBody"]["content"]["application/json"];
export type PatientPatch = paths["/api/patients/{patient_id}"]["patch"]["requestBody"]["content"]["application/json"];
export type Guardian = Schemas["GuardianOut"];
export type GuardianIn = Schemas["GuardianIn"];
export type ConsentsResponse = Schemas["ConsentsResponse"];
export type ConsentIn = Schemas["ConsentIn"];
export type Duplicate = Schemas["DuplicateOut"];
export type EnquiryIn = Schemas["EnquiryIn"];
export type EnquiryOut = Schemas["EnquiryOut"];

export type PatientCreateInput = Pick<PatientCreate, "first_name" | "last_name"> & Partial<PatientCreate>;
export type PatientPatchInput = Partial<PatientPatch>;
export type GuardianInput = Pick<GuardianIn, "relationship"> & {
  guardian_patient_id?: string;
  contact?: Pick<Schemas["ContactIn"], "full_name"> & Partial<Schemas["ContactIn"]>;
};
export type EnquiryInput = Pick<EnquiryIn, "clinic_id" | "source" | "message"> & Partial<EnquiryIn>;
export type ConsentInput = Pick<ConsentIn, "purpose" | "granted" | "source"> & Partial<ConsentIn>;

export type PatientListParams = Required<NonNullable<PatientListOperation["parameters"]["query"]>>;

type MergedBody = Schemas["MergedResponse"];
type ConflictBody = Schemas["ConflictResponse"];

export function mergedInto(error: unknown): string | null {
  if (error instanceof ApiError && error.status === 410) {
    const id = (error.body as Partial<MergedBody> | undefined)?.merged_into;
    if (typeof id === "string") return id;
  }
  return null;
}

export function duplicatesOf(error: unknown): Duplicate[] | null {
  if (error instanceof ApiError && error.status === 409 && error.code === "possible_duplicates") {
    return (error.body as Partial<ConflictBody> | undefined)?.duplicates ?? [];
  }
  return null;
}

export function usePatients(params: PatientListParams, enabled = true) {
  return useQuery<PatientList, ApiError>({
    queryKey: ["patients", params],
    enabled,
    queryFn: () => {
      const sp = new URLSearchParams({
        page: String(params.page),
        page_size: String(params.page_size),
      });
      if (params.q) sp.set("q", params.q);
      return apiFetch<PatientList>(`/api/patients?${sp.toString()}`);
    },
  });
}

export function usePatient(id: PatientDetailOperation["parameters"]["path"]["patient_id"]) {
  return useQuery<PatientDetail, ApiError>({
    queryKey: ["patient", id],
    queryFn: () => apiFetch<PatientDetail>(`/api/patients/${id}`),
    retry: false,
  });
}

export function useConsents(id: string) {
  return useQuery<ConsentsResponse, ApiError>({
    queryKey: ["patient", id, "consents"],
    queryFn: () => apiFetch<ConsentsResponse>(`/api/patients/${id}/consents`),
    retry: false,
  });
}

export function useCreatePatient() {
  const qc = useQueryClient();
  return useMutation<PatientDetail, ApiError, PatientCreateInput>({
    mutationFn: (body) => apiFetch<PatientDetail>("/api/patients", { method: "POST", body }),
    onSuccess: async (p) => {
      qc.setQueryData(["patient", p.id], p);
      await qc.invalidateQueries({ queryKey: ["patients"] });
    },
  });
}

export function useUpdatePatient(id: string) {
  const qc = useQueryClient();
  return useMutation<PatientDetail, ApiError, PatientPatchInput>({
    mutationFn: (body) => apiFetch<PatientDetail>(`/api/patients/${id}`, { method: "PATCH", body }),
    onError: refreshOnMerge(qc, id),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["patient", id] }),
        qc.invalidateQueries({ queryKey: ["patients"] }),
      ]);
    },
  });
}

export async function revealOib(id: string): Promise<string | null> {
  const { oib } = await apiFetch<Schemas["RevealOibResponse"]>(`/api/patients/${id}/reveal-oib`, { method: "POST" });
  return oib;
}

export async function lookupPatientByOib(oib: string, signal: AbortSignal): Promise<string | null> {
  const body: PatientOibLookupOperation["requestBody"]["content"]["application/json"] = { oib };
  const result = await apiFetch<PatientOibLookupResult>("/api/patients/lookup-oib", { method: "POST", body, signal });
  return result.patient_id;
}

function refreshOnMerge(client: ReturnType<typeof useQueryClient>, id: string) {
  return (error: ApiError) => {
    if (mergedInto(error)) return client.invalidateQueries({ queryKey: ["patient", id] });
  };
}

export function useAddGuardian(id: string) {
  const qc = useQueryClient();
  return useMutation<Guardian, ApiError, GuardianInput>({
    mutationFn: (body) =>
      apiFetch<Guardian>(`/api/patients/${id}/guardians`, { method: "POST", body }),
    onError: refreshOnMerge(qc, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient"] }),
  });
}

export function useRemoveGuardian(id: string) {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (linkId) =>
      apiFetch<void>(`/api/patients/${id}/guardians/${linkId}`, { method: "DELETE" }),
    onError: refreshOnMerge(qc, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient"] }),
  });
}

export function useRecordConsent(id: string) {
  const qc = useQueryClient();
  return useMutation<Schemas["ConsentOut"], ApiError, ConsentInput>({
    mutationFn: (body) =>
      apiFetch<Schemas["ConsentOut"]>(`/api/patients/${id}/consents`, { method: "POST", body }),
    onError: refreshOnMerge(qc, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", id] }),
  });
}

const PEOPLE_ERRORS = [
  "oib_taken",
  "merged",
  "not_found",
  "forbidden",
  "validation_error",
  "network_error",
  "unauthenticated",
  "possible_duplicates",
];

export function peopleErrorKey(error: unknown): string {
  const code = error instanceof ApiError ? error.code : "";
  return PEOPLE_ERRORS.includes(code) ? `people.errors.${code}` : "people.errors.unknown";
}

export function useCreateEnquiry(id: string) {
  const qc = useQueryClient();
  return useMutation<EnquiryOut, ApiError, EnquiryInput>({
    mutationFn: (body) =>
      apiFetch<EnquiryOut>(`/api/patients/${id}/enquiries`, { method: "POST", body }),
    onError: refreshOnMerge(qc, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", id, "enquiries"] }),
  });
}

export function usePatientEnquiries(id: string, page: number, pageSize: number) {
  return useQuery<PatientEnquiryHistory, ApiError>({
    queryKey: ["patient", id, "enquiries", page, pageSize],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      return apiFetch<PatientEnquiryHistory>(`/api/patients/${id}/enquiries?${params}`, { signal });
    },
    retry: false,
    refetchOnWindowFocus: false,
  });
}
