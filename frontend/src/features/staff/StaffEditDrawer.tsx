import { Alert, Button, Drawer, Group, Stack, Switch, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { staffErrorKey, useUpdateStaff, type Clinic, type StaffMember, type StaffPatch } from "./api";
import { StaffAssignmentsFields, validateClinics, validateFullName, validateRoles } from "./StaffAssignmentsFields";

export default function StaffEditDrawer({
  member,
  clinics,
  onClose,
}: {
  member: StaffMember;
  clinics: Clinic[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const update = useUpdateStaff(member.id);
  const initialValues = {
    full_name: member.full_name,
    roles: member.roles,
    clinic_ids: member.clinics.map((clinic) => clinic.id),
    is_active: member.is_active,
  };
  const form = useForm({
    initialValues,
    validate: {
      full_name: (value) => (value === initialValues.full_name ? null : validateFullName(value)),
      roles: (value) => (value === initialValues.roles ? null : validateRoles(value)),
      clinic_ids: (value) => (value.length === 0 && initialValues.clinic_ids.length === 0 ? null : validateClinics(value)),
    },
  });

  function submit(values: typeof initialValues) {
    if (update.isPending || !form.isDirty()) return;
    const patch: StaffPatch = {};
    if (form.isDirty("full_name")) patch.full_name = values.full_name.trim();
    if (form.isDirty("roles")) patch.roles = values.roles;
    if (form.isDirty("clinic_ids")) patch.clinic_ids = values.clinic_ids;
    if (form.isDirty("is_active")) patch.is_active = values.is_active;
    update.mutate(patch, { onSuccess: onClose });
  }

  return (
    <Drawer
      opened
      onClose={onClose}
      title={t("staff.editTitle")}
      withCloseButton={!update.isPending}
      closeOnEscape={!update.isPending}
      closeOnClickOutside={!update.isPending}
    >
      <form onSubmit={form.onSubmit(submit)} noValidate>
        <Stack>
          {update.error && <Alert color="red" role="alert">{t(staffErrorKey(update.error))}</Alert>}
          <TextInput
            label={t("staff.fullName")}
            maxLength={200}
            disabled={update.isPending}
            {...form.getInputProps("full_name")}
            error={form.errors.full_name && t(String(form.errors.full_name))}
          />
          <StaffAssignmentsFields form={form} clinics={clinics} disabled={update.isPending} />
          <Switch
            label={t("staff.active")}
            disabled={update.isPending}
            {...form.getInputProps("is_active", { type: "checkbox" })}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} disabled={update.isPending}>{t("common.cancel")}</Button>
            <Button type="submit" loading={update.isPending} disabled={!form.isDirty()}>{t("common.save")}</Button>
          </Group>
        </Stack>
      </form>
    </Drawer>
  );
}
