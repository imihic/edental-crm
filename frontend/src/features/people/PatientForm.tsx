import { Alert, Button, Group, NativeSelect, Stack, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { zod4Resolver as zodResolver } from "mantine-form-zod-resolver";
import { useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMe } from "../../api/auth";
import { ApiError } from "../../api/client";
import {
  duplicatesOf,
  peopleErrorKey,
  useCreatePatient,
  useUpdatePatient,
  type Duplicate,
  type PatientCreateInput,
  type PatientDetail,
  type PatientPatchInput,
} from "./api";
import DuplicateWarningDialog from "./DuplicateWarningDialog";
import { patientFormSchema, type PatientFormValues } from "./schemas";

const FIELD_NAMES = [
  "first_name",
  "last_name",
  "date_of_birth",
  "phone",
  "email",
  "oib",
  "address",
  "notes",
  "preferred_language",
  "preferred_clinic_id",
];

function initialValues(p?: PatientDetail): PatientFormValues {
  return {
    first_name: p?.first_name ?? "",
    last_name: p?.last_name ?? "",
    date_of_birth: p?.date_of_birth ?? "",
    phone: p?.phone ?? "",
    email: p?.email ?? "",
    oib: "",
    address: p?.address ?? "",
    notes: p?.notes ?? "",
    preferred_language: p?.preferred_language === "hr" ? "hr" : "en",
    preferred_clinic_id: p?.preferred_clinic?.id ?? "",
  };
}

const orNull = (v: string) => (v === "" ? null : v);

export default function PatientForm({
  patient,
  defaults,
  createPatient,
  duplicateActionLabel,
  errorKey = peopleErrorKey,
  onSaved,
  onCancel,
}: {
  patient?: PatientDetail;
  defaults?: Partial<PatientFormValues>;
  createPatient?: (body: PatientCreateInput) => Promise<PatientDetail>;
  duplicateActionLabel?: string;
  errorKey?: (error: unknown) => string;
  onSaved: (p: PatientDetail) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const me = useMe();
  const create = useCreatePatient();
  const update = useUpdatePatient(patient?.id ?? "");
  const [warning, setWarning] = useState<{ duplicates: Duplicate[]; values: PatientFormValues } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const active = useRef(false);
  const form = useForm<PatientFormValues>({
    initialValues: { ...initialValues(patient), ...defaults },
    validate: zodResolver(patientFormSchema, { errorPriority: "first" }),
  });
  const tr = (msg: unknown) => (typeof msg === "string" ? t(msg) : undefined);
  const clinics = me.data?.organization_clinics ?? [];

  useLayoutEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  function cancel() {
    active.current = false;
    onCancel();
  }

  async function save(v: PatientFormValues, confirmDuplicates: boolean) {
    if (busy || !active.current) return;
    setError(null);
    setBusy(true);
    const body: PatientCreateInput = {
      first_name: v.first_name,
      last_name: v.last_name,
      date_of_birth: orNull(v.date_of_birth),
      phone: orNull(v.phone),
      email: orNull(v.email),
      oib: orNull(v.oib),
      address: orNull(v.address),
      notes: orNull(v.notes),
      preferred_language: v.preferred_language,
      preferred_clinic_id: orNull(v.preferred_clinic_id),
    };
    try {
      let saved: PatientDetail;
      if (patient) {
        const changes: PatientPatchInput = Object.fromEntries(
          Object.entries(body).filter(([field, value]) => form.isDirty(field) && (field !== "oib" || value)),
        );
        saved = Object.keys(changes).length ? await update.mutateAsync(changes) : patient;
      } else {
        if (confirmDuplicates) body.confirm_duplicates = true;
        saved = await (createPatient ?? create.mutateAsync)(body);
      }
      if (active.current) {
        setWarning(null);
        onSaved(saved);
      }
    } catch (e) {
      if (!active.current) return;
      const dups = duplicatesOf(e);
      if (dups) {
        setWarning({ duplicates: dups, values: v });
        return;
      }
      setWarning(null);
      if (e instanceof ApiError && e.code === "oib_taken") {
        form.setFieldError("oib", "people.errors.oib_taken");
      } else if (e instanceof ApiError && e.code === "validation_error" && e.fields?.length) {
        for (const f of e.fields) {
          if (FIELD_NAMES.includes(f)) form.setFieldError(f, "people.validation.fieldInvalid");
        }
      } else {
        setError(e);
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={form.onSubmit((v) => void save(v, false))} noValidate>
        <Stack>
          {error !== null && <Alert color="red">{t(errorKey(error))}</Alert>}
          <Group grow align="flex-start">
            <TextInput
              label={t("people.fields.firstName")}
              aria-required
              {...form.getInputProps("first_name")}
              error={tr(form.errors.first_name)}
            />
            <TextInput
              label={t("people.fields.lastName")}
              aria-required
              {...form.getInputProps("last_name")}
              error={tr(form.errors.last_name)}
            />
          </Group>
          <TextInput
            type="date"
            label={t("people.fields.dateOfBirth")}
            {...form.getInputProps("date_of_birth")}
            error={tr(form.errors.date_of_birth)}
          />
          <TextInput
            label={t("people.fields.oib")}
            inputMode="numeric"
            maxLength={11}
            placeholder={patient?.oib_masked ?? undefined}
            {...form.getInputProps("oib")}
            error={tr(form.errors.oib)}
          />
          <Group grow align="flex-start">
            <TextInput
              label={t("people.fields.phone")}
              {...form.getInputProps("phone")}
              error={tr(form.errors.phone)}
            />
            <TextInput
              label={t("people.fields.email")}
              {...form.getInputProps("email")}
              error={tr(form.errors.email)}
            />
          </Group>
          <TextInput
            label={t("people.fields.address")}
            {...form.getInputProps("address")}
            error={tr(form.errors.address)}
          />
          <Textarea
            label={t("people.fields.notes")}
            {...form.getInputProps("notes")}
            error={tr(form.errors.notes)}
          />
          <Group grow align="flex-start">
            <NativeSelect
              label={t("people.fields.preferredLanguage")}
              data={[
                { value: "hr", label: t("people.languages.hr") },
                { value: "en", label: t("people.languages.en") },
              ]}
              {...form.getInputProps("preferred_language")}
            />
            {clinics.length > 0 && (
              <NativeSelect
                label={t("people.fields.preferredClinic")}
                data={[{ value: "", label: "-" }, ...clinics.map((c) => ({ value: c.id, label: c.name }))]}
                {...form.getInputProps("preferred_clinic_id")}
              />
            )}
          </Group>
          <Group justify="flex-end">
            <Button variant="default" onClick={cancel}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={busy && warning === null} disabled={warning !== null}>
              {t("common.save")}
            </Button>
          </Group>
        </Stack>
      </form>
      {warning && (
        <DuplicateWarningDialog
          duplicates={warning.duplicates}
          busy={busy}
          actionLabel={duplicateActionLabel}
          onClose={() => setWarning(null)}
          onCreateAnyway={() => void save(warning.values, true)}
        />
      )}
    </>
  );
}
