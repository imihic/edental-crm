import { Alert, Badge, Button, Card, Group, List, Modal, NativeSelect, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { peopleErrorKey, useConsents, useRecordConsent, type PatientDetail } from "./api";
import { useLeadConsents, useRecordLeadConsent, type LeadDetail } from "./leadApi";

const STATE_COLOR = { granted: "green", withdrawn: "red", unknown: "gray" } as const;
const SOURCES = ["paper", "verbal", "form"] as const;

type ConsentRecord = ReturnType<typeof useRecordConsent>;

function RecordConsentDialog({ guardians, record, onClose }: {
  guardians?: PatientDetail["guardians"];
  record: ConsentRecord;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [granted, setGranted] = useState("true");
  const [source, setSource] = useState<(typeof SOURCES)[number]>("paper");
  const [linkId, setLinkId] = useState("");
  const [missingGuardian, setMissingGuardian] = useState(false);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (guardians && linkId === "") {
      setMissingGuardian(true);
      return;
    }
    record.mutate(
      {
        purpose: "marketing",
        granted: granted === "true",
        source,
        ...(guardians ? { given_by_guardian_link_id: linkId } : {}),
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Modal opened onClose={onClose} title={t("people.consent.record")}>
      <form onSubmit={submit} noValidate>
        <Stack>
          {record.error && <Alert color="red">{t(peopleErrorKey(record.error))}</Alert>}
          <NativeSelect
            label={t("people.consent.decision")}
            value={granted}
            onChange={(e) => setGranted(e.currentTarget.value)}
            data={[
              { value: "true", label: t("people.consent.grant") },
              { value: "false", label: t("people.consent.withdraw") },
            ]}
          />
          <NativeSelect
            label={t("people.consent.source")}
            value={source}
            onChange={(e) => setSource(e.currentTarget.value as (typeof SOURCES)[number])}
            data={SOURCES.map((s) => ({ value: s, label: t(`people.consent.sources.${s}`) }))}
          />
          {guardians && (
            <NativeSelect
              label={t("people.consent.guardian")}
              value={linkId}
              onChange={(e) => {
                setLinkId(e.currentTarget.value);
                setMissingGuardian(false);
              }}
              error={missingGuardian ? t("people.consent.guardianRequired") : undefined}
              data={[
                { value: "", label: "-" },
                ...guardians.map((g) => ({ value: g.id, label: g.display_name })),
              ]}
            />
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={record.isPending}>
              {t("common.save")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

export default function ConsentPanel({ patient }: { patient: PatientDetail }) {
  const consents = useConsents(patient.id);
  const record = useRecordConsent(patient.id);
  return <ConsentCard consent={patient.consent} consents={consents} record={record}
    guardians={patient.is_minor ? patient.guardians : undefined} />;
}

export function LeadConsentPanel({ lead }: { lead: LeadDetail }) {
  const consents = useLeadConsents(lead.id);
  const record = useRecordLeadConsent(lead.id);
  return <ConsentCard consent={lead.consent} consents={consents} record={record} />;
}

function ConsentCard({ consent, consents, record, guardians }: {
  consent: PatientDetail["consent"];
  consents: ReturnType<typeof useConsents>;
  record: ConsentRecord;
  guardians?: PatientDetail["guardians"];
}) {
  const { t, i18n } = useTranslation();
  const [recording, setRecording] = useState(false);
  const state = consents.data?.current.marketing ?? consent.marketing ?? "unknown";

  return (
    <Card withBorder component="section" aria-labelledby="consent-title">
      <Stack>
        <Group justify="space-between">
          <Title order={4} id="consent-title">
            {t("people.consent.title")}
          </Title>
          <Button variant="light" size="compact-md" disabled={record.isPending}
            onClick={() => { record.reset(); setRecording(true); }}>
            {t("people.consent.record")}
          </Button>
        </Group>
        <Group gap="xs">
          <Text>{t("people.consent.marketing")}:</Text>
          <Badge color={STATE_COLOR[state]}>{t(`people.consent.states.${state}`)}</Badge>
        </Group>
        {consents.error && <Alert color="red">{t(peopleErrorKey(consents.error))}</Alert>}
        {consents.data && consents.data.history.length > 0 && (
          <List spacing={4}>
            {consents.data.history.map((c) => (
              <List.Item key={c.id}>
                {new Date(c.recorded_at).toLocaleString(i18n.language)} -{" "}
                {c.granted ? t("people.consent.granted") : t("people.consent.withdrawn")} (
                {t(`people.consent.sources.${c.source}`, { defaultValue: c.source })})
              </List.Item>
            ))}
          </List>
        )}
      </Stack>
      {recording && <RecordConsentDialog guardians={guardians} record={record} onClose={() => setRecording(false)} />}
    </Card>
  );
}
