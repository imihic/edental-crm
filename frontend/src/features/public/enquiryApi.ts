import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";

type Schemas = components["schemas"];
type PublicFormInfo = Schemas["PublicFormInfo"];
export type PublicEnquiryInput = Schemas["PublicEnquiryIn"];
type PublicEnquiryReceived = Schemas["PublicEnquiryReceived"];

const formPath = (key: string) => "/api/public/enquiry-forms/" + encodeURIComponent(key);

export function usePublicEnquiryForm(key: string) {
  return useQuery<PublicFormInfo, ApiError>({
    queryKey: ["public-enquiry-form", key],
    queryFn: () => apiFetch<PublicFormInfo>(formPath(key)),
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useSubmitPublicEnquiry(key: string) {
  return useMutation<PublicEnquiryReceived, ApiError, PublicEnquiryInput>({
    mutationFn: (body) =>
      apiFetch<PublicEnquiryReceived>(formPath(key) + "/enquiries", { method: "POST", body }),
  });
}
