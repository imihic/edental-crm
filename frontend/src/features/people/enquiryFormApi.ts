import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";

type EnquiryForm = components["schemas"]["EnquiryFormOut"];

const formKey = (clinicId: string) => ["enquiry-form", clinicId];
const formPath = (clinicId: string) => "/api/clinics/" + encodeURIComponent(clinicId) + "/enquiry-form";

export function useEnquiryForm(clinicId: string) {
  return useQuery<EnquiryForm, ApiError>({
    queryKey: formKey(clinicId),
    queryFn: () => apiFetch<EnquiryForm>(formPath(clinicId)),
    retry: false,
  });
}

export function useRegenerateEnquiryForm(clinicId: string) {
  const client = useQueryClient();
  return useMutation<EnquiryForm, ApiError, void>({
    mutationFn: () => apiFetch<EnquiryForm>(formPath(clinicId) + "/regenerate", { method: "POST", body: {} }),
    onSuccess: async (form) => {
      const queryKey = formKey(clinicId);
      await client.cancelQueries({ queryKey });
      client.setQueryData(queryKey, form);
    },
  });
}
