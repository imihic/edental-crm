import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorKey } from "../../api/auth";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";

type Schemas = components["schemas"];
export type StaffMember = Schemas["StaffOut"];
export type Clinic = Schemas["ClinicOut"];
export type Role = Schemas["Role"];
export type StaffPatch = Partial<Schemas["StaffPatchIn"]>;
export type InvitationInput = Schemas["InvitationIn"];
export type InvitationCreated = Schemas["InvitationCreatedOut"];

const staffKey = ["staff"];
const invitationsKey = ["invitations"];

export function useStaff() {
  return useQuery({
    queryKey: staffKey,
    queryFn: () => apiFetch<Schemas["StaffListOut"]>("/api/staff"),
    retry: false,
  });
}

export function useInvitations() {
  return useQuery({
    queryKey: invitationsKey,
    queryFn: () => apiFetch<Schemas["InvitationListOut"]>("/api/invitations"),
    retry: false,
  });
}

export function useUpdateStaff(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: StaffPatch) => apiFetch<StaffMember>(`/api/staff/${id}`, { method: "PATCH", body }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: staffKey }),
        client.invalidateQueries({ queryKey: ["me"] }),
      ]);
    },
  });
}

export function createInvitation(body: InvitationInput) {
  return apiFetch<InvitationCreated>("/api/invitations", { method: "POST", body });
}

export function useRevokeInvitation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/invitations/${id}`, { method: "DELETE" }),
    onSettled: () => client.invalidateQueries({ queryKey: invitationsKey }),
  });
}

export function staffErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "last_manager":
      case "already_staff":
      case "already_invited":
        return `staff.errors.${error.code}`;
      case "invitation_used":
        return "invitation.errors.invitation_used";
      case "not_found":
        return "people.errors.not_found";
    }
  }
  return errorKey(error);
}
