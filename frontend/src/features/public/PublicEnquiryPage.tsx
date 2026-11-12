import {
  Alert,
  Button,
  Checkbox,
  Container,
  Group,
  Loader,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
  VisuallyHidden,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import type { ApiError } from "../../api/client";
import { usePublicEnquiryForm, useSubmitPublicEnquiry } from "./enquiryApi";

function publicErrorKey(error: ApiError) {
  if (error.status === 404) return "publicEnquiry.errors.unavailable";
  if (error.status === 422) {
    return error.fields?.includes("phone") ? "publicEnquiry.errors.invalidPhone" : "publicEnquiry.errors.invalidInput";
  }
  return "publicEnquiry.errors.requestFailed";
}

function EnquiryForm({ formKey }: { formKey: string }) {
  const { t } = useTranslation();
  const submit = useSubmitPublicEnquiry(formKey);
  const form = useForm({
    initialValues: {
      full_name: "",
      phone: "",
      email: "",
      message: "",
      preferred_contact_time: "",
      marketing_consent: false,
      website: "",
    },
    validate: {
      full_name: (value) => value.trim() ? null : t("publicEnquiry.validation.fullNameRequired"),
      message: (value) => value.trim() ? null : t("publicEnquiry.validation.messageRequired"),
      email: (value, values) => {
        const email = value.trim();
        if (!email) return values.phone.trim() ? null : t("publicEnquiry.validation.contactRequired");
        return /^[^@\s]+@[^@\s]+\.[^@\s.]+$/.test(email) ? null : t("publicEnquiry.validation.emailInvalid");
      },
    },
  });

  if (submit.isSuccess) return <Alert color="green">{t("publicEnquiry.thanks")}</Alert>;
  if (submit.error?.status === 404) return <Alert color="red">{t(publicErrorKey(submit.error))}</Alert>;

  return (
    <form
      noValidate
      onSubmit={form.onSubmit((values) => {
        submit.mutate({
          full_name: values.full_name.trim(),
          phone: values.phone.trim() || null,
          email: values.email.trim() || null,
          message: values.message.trim(),
          preferred_contact_time: values.preferred_contact_time.trim() || null,
          marketing_consent: values.marketing_consent,
          website: values.website,
        });
      })}
    >
      <Stack>
        <Title order={2}>{t("publicEnquiry.title")}</Title>
        {submit.error && <Alert color="red">{t(publicErrorKey(submit.error))}</Alert>}
        <TextInput
          label={t("publicEnquiry.fullName")}
          required
          autoComplete="name"
          maxLength={200}
          {...form.getInputProps("full_name")}
        />
        <Text size="sm" c="dimmed">{t("publicEnquiry.contactHint")}</Text>
        <TextInput
          label={t("publicEnquiry.phone")}
          type="tel"
          autoComplete="tel"
          maxLength={40}
          {...form.getInputProps("phone")}
        />
        <TextInput
          label={t("publicEnquiry.email")}
          type="email"
          autoComplete="email"
          maxLength={254}
          {...form.getInputProps("email")}
        />
        <Textarea label={t("publicEnquiry.message")} required maxLength={2000} {...form.getInputProps("message")} />
        <TextInput
          label={t("publicEnquiry.preferredContactTime")}
          maxLength={100}
          {...form.getInputProps("preferred_contact_time")}
        />
        <Checkbox
          label={t("publicEnquiry.marketingConsent")}
          description={t("publicEnquiry.marketingDescription")}
          {...form.getInputProps("marketing_consent", { type: "checkbox" })}
        />
        <VisuallyHidden aria-hidden="true">
          <input name="website" tabIndex={-1} autoComplete="off" maxLength={2000} {...form.getInputProps("website")} />
        </VisuallyHidden>
        <Group>
          <Button type="submit" loading={submit.isPending}>{t("publicEnquiry.send")}</Button>
        </Group>
      </Stack>
    </form>
  );
}

export default function PublicEnquiryPage() {
  const { key = "" } = useParams();
  const info = usePublicEnquiryForm(key);
  const { t, i18n } = useTranslation();

  return (
    <Container component="main" size="xs" py="xl" lang={i18n.resolvedLanguage}>
      <Stack>
        {info.isPending && <Loader aria-label={t("common.loading")} />}
        {info.error && <Alert color="red">{t(publicErrorKey(info.error))}</Alert>}
        {info.data && !info.error && (
          <>
            <Title order={1}>{info.data.clinic_name}</Title>
            <EnquiryForm key={key} formKey={key} />
          </>
        )}
      </Stack>
    </Container>
  );
}
