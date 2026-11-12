import { Alert, Button, Group, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { staffErrorKey, useInvitations, useRevokeInvitation, useStaff, type Clinic, type StaffMember } from "./api";
import InviteDialog from "./InviteDialog";
import StaffEditDrawer from "./StaffEditDrawer";

export default function StaffPage({ clinics }: { clinics: Clinic[] }) {
  const { t } = useTranslation();
  const staff = useStaff();
  const invitations = useInvitations();
  const revoke = useRevokeInvitation();
  const [editing, setEditing] = useState<StaffMember | null>(null);
  const [inviting, setInviting] = useState(false);
  const members = staff.data?.items ?? [];
  const pending = invitations.data?.items ?? [];

  return (
    <Stack gap="xl">
      <Stack>
        <Group justify="space-between">
          <Title order={2}>{t("staff.title")}</Title>
          <Button disabled={!staff.isSuccess} onClick={() => setInviting(true)}>{t("staff.invite")}</Button>
        </Group>
        {staff.isPending && <Text>{t("common.loading")}</Text>}
        {staff.error && <Alert color="red" role="alert">{t(staffErrorKey(staff.error))}</Alert>}
        {staff.data && members.length === 0 && <Text c="dimmed">{t("staff.empty")}</Text>}
        {members.length > 0 && (
          <Table.ScrollContainer minWidth={680}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("staff.fullName")}</Table.Th>
                  <Table.Th>{t("auth.login.email")}</Table.Th>
                  <Table.Th>{t("staff.roles")}</Table.Th>
                  <Table.Th>{t("staff.clinics")}</Table.Th>
                  <Table.Th>{t("staff.status")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {members.map((member) => (
                  <Table.Tr key={member.id}>
                    <Table.Td>{member.full_name}</Table.Td>
                    <Table.Td>{member.email}</Table.Td>
                    <Table.Td>{member.roles.map((role) => t(`roles.${role}`)).join(", ")}</Table.Td>
                    <Table.Td>{member.clinics.map((clinic) => clinic.name).join(", ")}</Table.Td>
                    <Table.Td>{t(member.is_active ? "staff.active" : "staff.inactive")}</Table.Td>
                    <Table.Td>
                      <Button size="compact-sm" variant="default" onClick={() => setEditing(member)}>{t("staff.edit")}</Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>

      <Stack>
        <Title order={3}>{t("staff.pendingInvitations")}</Title>
        {invitations.isPending && <Text>{t("common.loading")}</Text>}
        {invitations.error && <Alert color="red" role="alert">{t(staffErrorKey(invitations.error))}</Alert>}
        {revoke.error && <Alert color="red" role="alert">{t(staffErrorKey(revoke.error))}</Alert>}
        {invitations.data && pending.length === 0 && <Text c="dimmed">{t("staff.noInvitations")}</Text>}
        {pending.length > 0 && (
          <Table.ScrollContainer minWidth={480}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("staff.fullName")}</Table.Th>
                  <Table.Th>{t("auth.login.email")}</Table.Th>
                  <Table.Th>{t("staff.roles")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {pending.map((invitation) => (
                  <Table.Tr key={invitation.id}>
                    <Table.Td>{invitation.full_name}</Table.Td>
                    <Table.Td>{invitation.email}</Table.Td>
                    <Table.Td>{invitation.roles.map((role) => t(`roles.${role}`)).join(", ")}</Table.Td>
                    <Table.Td>
                      <Button
                        size="compact-sm"
                        variant="default"
                        disabled={revoke.isPending}
                        loading={revoke.isPending && revoke.variables === invitation.id}
                        onClick={() => revoke.mutate(invitation.id)}
                      >
                        {t("staff.revoke")}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>

      {editing && <StaffEditDrawer member={editing} clinics={clinics} onClose={() => setEditing(null)} />}
      {inviting && (
        <InviteDialog clinics={clinics} onClose={() => setInviting(false)} onCreated={() => void invitations.refetch()} />
      )}
    </Stack>
  );
}
