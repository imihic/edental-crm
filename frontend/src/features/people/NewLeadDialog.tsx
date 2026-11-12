import { Alert, Button, Group, Modal, NativeSelect, Stack, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { zod4Resolver } from "mantine-form-zod-resolver";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import type { Me } from "../../api/auth";
import { ApiError } from "../../api/client";
import { peopleErrorKey } from "./api";
import { useCreateLead, type LeadCreated } from "./leadApi";
import { contactSchema } from "./schemas";

const SOURCES = ["phone", "walk_in", "email", "other"] as const;
const leadFormSchema = contactSchema.extend({
  clinic_id: z.string(),
  source: z.enum(SOURCES),
  message: z.string().trim().min(1, "people.validation.messageRequired").max(2000, "people.validation.tooLong"),
  preferred_contact_time: z.string().trim().max(100, "people.validation.tooLong"),
});

type LeadFormValues = z.infer<typeof leadFormSchema>;

export default function NewLeadDialog({
  clinics,
  clinicId,
  onClose,
  onCreated,
}: {
  clinics: Me["clinics"];
  clinicId: string;
  onClose: () => void;
  onCreated: (result: LeadCreated) => void;
}) {
  const { t } = useTranslation();
  const create = useCreateLead();
  const form = useForm<LeadFormValues>({
    initialValues: {
      full_name: "", phone: "", email: "", clinic_id: clinicId, source: "phone",
      message: "", preferred_contact_time: "",
    },
    validate: zod4Resolver(leadFormSchema, { errorPriority: "first" }),
  });
  const clinic = form.values.clinic_id || clinics[0]?.id || "";
  const error = (field: keyof LeadFormValues) => {
    const message = form.errors[field];
    if (typeof message === "string") return t(message);
    if (create.error instanceof ApiError && create.error.fields?.includes(field)) {
      return t("people.validation.fieldInvalid");
    }
  };

  function submit(values: LeadFormValues) {
    if (!clinic || create.isPending) return;
    create.mutate({
      clinic_id: clinic,
      source: values.source,
      full_name: values.full_name.trim(),
      phone: values.phone.trim() || null,
      email: values.email.trim() || null,
      message: values.message.trim(),
      preferred_contact_time: values.preferred_contact_time.trim() || null,
    }, { onSuccess: onCreated });
  }

  return (
    <Modal opened onClose={onClose} title={t("people.leads.new")} size="lg"
      closeOnEscape={!create.isPending} closeOnClickOutside={!create.isPending} withCloseButton={!create.isPending}>
      <form onSubmit={form.onSubmit(submit)} noValidate>
        <Stack>
          {create.error && <Alert color="red">{t(peopleErrorKey(create.error))}</Alert>}
          <TextInput label={t("people.fields.fullName")} required maxLength={200}
            {...form.getInputProps("full_name")} error={error("full_name")} />
          <Group grow align="flex-start">
            <TextInput label={t("people.fields.phone")} type="tel" maxLength={40}
              {...form.getInputProps("phone")} error={error("phone")} />
            <TextInput label={t("people.fields.email")} type="email" maxLength={254}
              {...form.getInputProps("email")} error={error("email")} />
          </Group>
          <Group grow align="flex-start">
            <NativeSelect label={t("people.enquiries.clinic")} required
              data={clinics.map((c) => ({ value: c.id, label: c.name }))}
              {...form.getInputProps("clinic_id")} value={clinic} error={error("clinic_id")} />
            <NativeSelect label={t("people.enquiries.source")}
              data={SOURCES.map((source) => ({ value: source, label: t(`people.enquiries.sources.${source}`) }))}
              {...form.getInputProps("source")} />
          </Group>
          <Textarea label={t("people.enquiries.message")} required maxLength={2000}
            {...form.getInputProps("message")} error={error("message")} />
          <TextInput label={t("people.enquiries.preferredContactTime")} maxLength={100}
            {...form.getInputProps("preferred_contact_time")} error={error("preferred_contact_time")} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} disabled={create.isPending}>{t("common.cancel")}</Button>
            <Button type="submit" loading={create.isPending} disabled={!clinic}>{t("common.save")}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
