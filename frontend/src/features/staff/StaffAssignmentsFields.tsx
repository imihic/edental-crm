import { Checkbox, Group, MultiSelect } from "@mantine/core";
import type { UseFormReturnType } from "@mantine/form";
import { useTranslation } from "react-i18next";
import type { Clinic, Role } from "./api";

const roles: Role[] = ["receptionist", "dentist", "clinic_manager"];

type Assignments = { roles: Role[]; clinic_ids: string[] };

export function StaffAssignmentsFields<Values extends Assignments>({
  form,
  clinics,
  disabled,
}: {
  form: UseFormReturnType<Values>;
  clinics: Clinic[];
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const roleInput = form.getInputProps("roles");
  const clinicInput = form.getInputProps("clinic_ids");
  return (
    <>
      <Checkbox.Group {...roleInput} label={t("staff.roles")} error={roleInput.error && t(roleInput.error)}>
        <Group mt="xs">
          {roles.map((role) => (
            <Checkbox key={role} value={role} label={t(`roles.${role}`)} disabled={disabled} />
          ))}
        </Group>
      </Checkbox.Group>
      <MultiSelect
        {...clinicInput}
        label={t("staff.clinics")}
        data={clinics.map((clinic) => ({ value: clinic.id, label: clinic.name }))}
        error={clinicInput.error && t(clinicInput.error)}
        searchable
        maxValues={200}
        disabled={disabled}
      />
    </>
  );
}

export const validateFullName = (name: string) => (name.trim() ? null : "staff.validation.nameRequired");
export const validateRoles = (values: Role[]) => (values.length ? null : "staff.validation.rolesRequired");
export const validateClinics = (values: string[]) => (values.length ? null : "staff.validation.clinicsRequired");
