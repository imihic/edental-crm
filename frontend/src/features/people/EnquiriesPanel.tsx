import { Alert, Button, Card, Divider, Group, NativeSelect, Pagination, Stack, Text, TextInput, Textarea, Title } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import { useMe } from "../../api/auth";
import { mergedInto, peopleErrorKey, useCreateEnquiry, usePatientEnquiries, type EnquiryInput } from "./api";

const SOURCES: EnquiryInput["source"][] = ["phone", "walk_in", "email", "other"];
const PAGE_SIZE = 25;

export default function EnquiriesPanel({ patientId }: { patientId: string }) {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const create = useCreateEnquiry(patientId);
  const clinics = me.data?.organization_clinics ?? [];
  const [clinicId, setClinicId] = useState("");
  const [source, setSource] = useState<EnquiryInput["source"]>("phone");
  const [message, setMessage] = useState("");
  const [preferred, setPreferred] = useState("");
  const [messageError, setMessageError] = useState(false);
  const [saved, setSaved] = useState(false);
  const [page, setPage] = useState(1);
  const [lastPageCount, setLastPageCount] = useState(0);
  const history = usePatientEnquiries(patientId, page, PAGE_SIZE);
  const effectiveClinic = clinicId || me.data?.clinics[0]?.id || clinics[0]?.id || "";
  const pages = history.data ? Math.min(10_000, Math.ceil(history.data.total / PAGE_SIZE)) : lastPageCount;
  const keptPatientId = mergedInto(history.error);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (create.isPending || !effectiveClinic) return;
    setSaved(false);
    if (message.trim() === "") {
      setMessageError(true);
      return;
    }
    create.mutate(
      {
        clinic_id: effectiveClinic,
        source,
        message: message.trim(),
        ...(preferred.trim() ? { preferred_contact_time: preferred.trim() } : {}),
      },
      {
        onSuccess: () => {
          setSaved(true);
          setMessage("");
          setPreferred("");
          setPage(1);
        },
      },
    );
  }

  if (keptPatientId) return <Navigate to={`/patients/${keptPatientId}`} replace state={{ merged: true }} />;

  return (
    <Card withBorder component="section" aria-labelledby="enquiries-title">
      <Stack>
        <Title order={4} id="enquiries-title">{t("people.enquiries.title")}</Title>
        {history.isPending && <Text c="dimmed">{t("common.loading")}</Text>}
        {history.error && (
          <Alert color="red">
            <Group justify="space-between">
              <Text size="sm">{t(peopleErrorKey(history.error))}</Text>
              <Button size="compact-sm" variant="light" loading={history.isFetching} onClick={() => void history.refetch()}>
                {t("common.retry")}
              </Button>
            </Group>
          </Alert>
        )}
        {history.data?.total === 0 && <Text c="dimmed">{t("people.enquiries.empty")}</Text>}
        {history.data?.items.map((entry) => (
          <Stack component="article" key={entry.id} gap={4}>
            <Group gap="xs" c="dimmed">
              <Text size="sm">{t(`people.enquiries.sources.${entry.source}`)}</Text>
              <Text size="sm" component="time" dateTime={entry.received_at}>
                {new Date(entry.received_at).toLocaleString(i18n.language)}
              </Text>
              <Text size="sm">{clinics.find((clinic) => clinic.id === entry.clinic_id)?.name}</Text>
            </Group>
            <Text style={{ whiteSpace: "pre-wrap" }}>{entry.message}</Text>
            {entry.preferred_contact_time && (
              <Text size="sm">{t("people.enquiries.preferredContactTime")}: {entry.preferred_contact_time}</Text>
            )}
            {entry.marketing_consent_requested && (
              <Text size="sm" fw={500}>{t("people.enquiries.marketingConsentRequested")}</Text>
            )}
          </Stack>
        ))}
        {pages > 1 && (
          <Pagination
            size="sm"
            total={pages}
            value={page}
            onChange={(nextPage) => {
              setLastPageCount(pages);
              setPage(nextPage);
            }}
          />
        )}
        <Divider />
        <Stack component="form" onSubmit={submit}>
          {saved && <Alert color="green">{t("people.enquiries.saved")}</Alert>}
          {create.error && <Alert color="red">{t(peopleErrorKey(create.error))}</Alert>}
          <Group grow align="flex-start">
            {clinics.length > 1 && (
              <NativeSelect
                disabled={create.isPending}
                label={t("people.enquiries.clinic")}
                value={effectiveClinic}
                onChange={(e) => setClinicId(e.currentTarget.value)}
                data={clinics.map((c) => ({ value: c.id, label: c.name }))}
              />
            )}
            <NativeSelect
              disabled={create.isPending}
              label={t("people.enquiries.source")}
              value={source}
              onChange={(e) => setSource(e.currentTarget.value as EnquiryInput["source"])}
              data={SOURCES.map((s) => ({ value: s, label: t(`people.enquiries.sources.${s}`) }))}
            />
          </Group>
          <Textarea
            disabled={create.isPending}
            label={t("people.enquiries.message")}
            value={message}
            maxLength={2000}
            onChange={(e) => {
              setMessage(e.currentTarget.value);
              setMessageError(false);
            }}
            error={messageError ? t("people.validation.messageRequired") : undefined}
          />
          <TextInput
            disabled={create.isPending}
            label={t("people.enquiries.preferredContactTime")}
            value={preferred}
            maxLength={100}
            onChange={(e) => setPreferred(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button type="submit" loading={create.isPending} disabled={effectiveClinic === ""}>
              {t("people.enquiries.add")}
            </Button>
          </Group>
        </Stack>
      </Stack>
    </Card>
  );
}
