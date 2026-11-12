import { Alert, Button, Group, Modal, Stack, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useClipboard } from "@mantine/hooks";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { loginSchema } from "../auth/schemas";
import { createInvitation, staffErrorKey, type Clinic, type InvitationCreated, type InvitationInput } from "./api";
import { StaffAssignmentsFields, validateClinics, validateFullName, validateRoles } from "./StaffAssignmentsFields";

export default function InviteDialog({
  clinics,
  onClose,
  onCreated,
}: {
  clinics: Clinic[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t, i18n } = useTranslation();
  const clipboard = useClipboard();
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const form = useForm<InvitationInput>({
    initialValues: { email: "", full_name: "", roles: [], clinic_ids: [] },
    validate: {
      email: (email) => loginSchema.shape.email.safeParse(email).error?.issues[0]?.message,
      full_name: validateFullName,
      roles: validateRoles,
      clinic_ids: validateClinics,
    },
  });

  async function submit(values: InvitationInput) {
    if (pending) return;
    setPending(true);
    setError(undefined);
    try {
      const result = await createInvitation({ ...values, email: values.email.trim(), full_name: values.full_name.trim() });
      setCreated(result);
      onCreated();
    } catch (err) {
      setError(staffErrorKey(err));
    } finally {
      setPending(false);
    }
  }

  const close = () => {
    if (pending) return;
    clipboard.reset();
    onClose();
  };
  const link = created ? window.location.origin + created.url : "";

  return (
    <Modal
      opened
      onClose={close}
      title={t("staff.inviteTitle")}
      withCloseButton={!pending}
      closeOnEscape={!pending}
      closeOnClickOutside={!pending}
    >
      {created ? (
        <Stack>
          <Text>{t("staff.oneTimeLink")}</Text>
          <TextInput label={t("staff.link")} value={link} readOnly autoComplete="off" />
          <Text component="time" dateTime={created.expires_at}>
            {t("staff.expiresAt", {
              date: new Date(created.expires_at).toLocaleString(i18n.resolvedLanguage, {
                dateStyle: "medium",
                timeStyle: "short",
              }),
            })}
          </Text>
          {clipboard.error && <Alert color="red" role="alert">{t("staff.copyFailed")}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>{t("staff.done")}</Button>
            <Button onClick={() => clipboard.copy(link)}>{t(clipboard.copied ? "staff.copied" : "staff.copy")}</Button>
          </Group>
        </Stack>
      ) : (
        <form onSubmit={form.onSubmit(submit)} noValidate>
          <Stack>
            {error && <Alert color="red" role="alert">{t(error)}</Alert>}
            <TextInput
              label={t("auth.login.email")}
              type="email"
              maxLength={320}
              disabled={pending}
              {...form.getInputProps("email")}
              error={form.errors.email && t(String(form.errors.email))}
            />
            <TextInput
              label={t("staff.fullName")}
              maxLength={200}
              disabled={pending}
              {...form.getInputProps("full_name")}
              error={form.errors.full_name && t(String(form.errors.full_name))}
            />
            <StaffAssignmentsFields form={form} clinics={clinics} disabled={pending} />
            <Group justify="flex-end">
              <Button variant="default" onClick={close} disabled={pending}>{t("common.cancel")}</Button>
              <Button type="submit" loading={pending}>{t("staff.invite")}</Button>
            </Group>
          </Stack>
        </form>
      )}
    </Modal>
  );
}
