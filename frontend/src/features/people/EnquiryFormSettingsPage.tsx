import { Alert, Button, Card, Group, Loader, Modal, Stack, Tabs, Text, TextInput, Textarea, Title } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMe } from "../../api/auth";
import { peopleErrorKey } from "./api";
import { useEnquiryForm, useRegenerateEnquiryForm } from "./enquiryFormApi";

function CopyControl({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<"copied" | "copyFailed" | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setStatus("copied");
    } catch {
      setStatus("copyFailed");
    }
  }

  return (
    <Group>
      <Button variant="default" onClick={() => void copy()}>{label}</Button>
      <Text role="status" size="sm" c={status === "copyFailed" ? "red" : "dimmed"}>
        {status && t("people.enquiryForm." + status)}
      </Text>
    </Group>
  );
}

function ClinicEnquiryForm({ clinicId }: { clinicId: string }) {
  const { t } = useTranslation();
  const form = useEnquiryForm(clinicId);
  const regenerate = useRegenerateEnquiryForm(clinicId);
  const [confirm, setConfirm] = useState(false);
  const regenerateLabel = t("people.enquiryForm.regenerate");

  function closeConfirmation() {
    if (regenerate.isPending) return;
    regenerate.reset();
    setConfirm(false);
  }

  if (form.isPending) return <Loader aria-label={t("common.loading")} />;
  if (form.error || !form.data) {
    return (
      <Stack align="flex-start">
        <Alert color="red">{t(peopleErrorKey(form.error))}</Alert>
        <Button variant="default" onClick={() => void form.refetch()}>{t("common.retry")}</Button>
      </Stack>
    );
  }

  const url = window.location.origin + form.data.path;
  const embedTitle = t("people.enquiryForm.embedTitle");
  const embed = '<iframe src="' + url + '" title="' + embedTitle + '" width="100%" height="720"></iframe>';
  return (
    <Stack>
      {!form.data.enabled && <Alert color="yellow">{t("people.enquiryForm.disabled")}</Alert>}
      <TextInput label={t("people.enquiryForm.publicLink")} value={url} readOnly />
      <CopyControl key={url} value={url} label={t("people.enquiryForm.copyLink")} />
      <Textarea label={t("people.enquiryForm.embedCode")} value={embed} readOnly autosize />
      <CopyControl key={embed} value={embed} label={t("people.enquiryForm.copyCode")} />
      <Group>
        <Button color="red" variant="outline" onClick={() => setConfirm(true)}>{regenerateLabel}</Button>
      </Group>
      <Modal opened={confirm} onClose={closeConfirmation} title={regenerateLabel} withCloseButton={!regenerate.isPending}>
        <Stack>
          <Text>{t("people.enquiryForm.regenerateWarning")}</Text>
          {regenerate.error && <Alert color="red">{t(peopleErrorKey(regenerate.error))}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" disabled={regenerate.isPending} onClick={closeConfirmation}>
              {t("common.cancel")}
            </Button>
            <Button color="red" loading={regenerate.isPending} onClick={() => {
              regenerate.mutate(undefined, { onSuccess: () => setConfirm(false) });
            }}>
              {regenerateLabel}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

export default function EnquiryFormSettingsPage() {
  const { t } = useTranslation();
  const me = useMe();
  const [selected, setSelected] = useState<string | null>(null);
  const clinics = me.data?.organization_clinics ?? [];
  const active = clinics.find((clinic) => clinic.id === selected)?.id ?? clinics[0]?.id ?? null;

  return (
    <Stack>
      <Title order={1}>{t("people.enquiryForm.title")}</Title>
      {me.isPending ? (
        <Loader aria-label={t("common.loading")} />
      ) : me.error ? (
        <Alert color="red">{t(peopleErrorKey(me.error))}</Alert>
      ) : clinics.length === 0 ? (
        <Text c="dimmed">{t("people.enquiryForm.noClinics")}</Text>
      ) : (
        <Card withBorder>
          <Tabs value={active} onChange={setSelected} keepMounted={false}>
            <Tabs.List aria-label={t("people.enquiryForm.clinics")}>
              {clinics.map((clinic) => <Tabs.Tab key={clinic.id} value={clinic.id}>{clinic.name}</Tabs.Tab>)}
            </Tabs.List>
            {clinics.map((clinic) => (
              <Tabs.Panel key={clinic.id} value={clinic.id} pt="md">
                <ClinicEnquiryForm clinicId={clinic.id} />
              </Tabs.Panel>
            ))}
          </Tabs>
        </Card>
      )}
    </Stack>
  );
}
