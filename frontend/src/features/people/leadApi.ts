import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Me } from "../../api/auth";
import { apiFetch, ApiError } from "../../api/client";
import type { components, paths } from "../../api/schema";
import { peopleErrorKey, type ConsentInput, type PatientCreateInput, type PatientDetail } from "./api";

type Schemas = components["schemas"];
export type LeadDetail = Schemas["LeadDetail"];
export type LeadStage = LeadDetail["stage"];
export type LostReason = NonNullable<LeadDetail["lost_reason"]>;
type LeadCreate = Schemas["LeadCreate"];
export type LeadCreateInput = Pick<LeadCreate, "full_name" | "clinic_id" | "source" | "message"> & Partial<LeadCreate>;
export type LeadCreated = Schemas["LeadCreated"];
type LeadListParams = NonNullable<paths["/api/leads"]["get"]["parameters"]["query"]>;
type LeadStageInput = Pick<Schemas["LeadStageIn"], "stage"> & Partial<Schemas["LeadStageIn"]>;

export function canMergeRecords(me: Me | null | undefined) {
  return me?.staff.roles.some((role) => role === "receptionist" || role === "clinic_manager") ?? false;
}

export function peopleActionErrorKey(error: unknown) {
  if (error instanceof ApiError && (error.code === "invalid_transition" || error.code === "invalid_merge")) {
    return `people.errors.${error.code}`;
  }
  return peopleErrorKey(error);
}

export function useLeads(params: LeadListParams) {
  return useQuery({
    queryKey: ["leads", params],
    queryFn: () => {
      const search = new URLSearchParams();
      if (params.q) search.set("q", params.q);
      if (params.clinic_id) search.set("clinic_id", params.clinic_id);
      if (params.stage) search.set("stage", params.stage);
      if (params.page) search.set("page", String(params.page));
      if (params.page_size) search.set("page_size", String(params.page_size));
      return apiFetch<Schemas["LeadListResponse"]>(`/api/leads?${search}`);
    },
    placeholderData: (previous) => previous,
  });
}

export function useLead(id: string) {
  return useQuery({
    queryKey: ["lead", id],
    queryFn: () => apiFetch<LeadDetail>(`/api/leads/${id}`),
    retry: false,
  });
}

export function useCreateLead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: LeadCreateInput) => apiFetch<LeadCreated>("/api/leads", { method: "POST", body }),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["leads"] });
      if (result.attached_to === "lead" && result.lead_id) {
        void client.invalidateQueries({ queryKey: ["lead", result.lead_id] });
      }
    },
  });
}

export function useChangeLeadStage(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: LeadStageInput) => apiFetch<LeadDetail>(`/api/leads/${id}/stage`, { method: "POST", body }),
    onSuccess: (lead) => {
      client.setQueryData(["lead", id], lead);
      void client.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useConvertLead(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PatientCreateInput) =>
      apiFetch<PatientDetail>(`/api/leads/${id}/convert`, { method: "POST", body }),
    onSuccess: (patient) => {
      client.setQueryData(["patient", patient.id], patient);
      void client.invalidateQueries({ queryKey: ["lead", id] });
      void client.invalidateQueries({ queryKey: ["leads"] });
      void client.invalidateQueries({ queryKey: ["patients"] });
    },
  });
}

export function useLeadConsents(id: string) {
  return useQuery<Schemas["ConsentsResponse"], ApiError>({
    queryKey: ["lead", id, "consents"],
    queryFn: () => apiFetch<Schemas["ConsentsResponse"]>(`/api/leads/${id}/consents`),
    retry: false,
  });
}

export function useRecordLeadConsent(id: string) {
  const client = useQueryClient();
  return useMutation<Schemas["ConsentOut"], ApiError, ConsentInput>({
    mutationFn: (body: ConsentInput) =>
      apiFetch<Schemas["ConsentOut"]>(`/api/leads/${id}/consents`, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["lead", id] }),
  });
}
