import { Alert, Anchor, Badge, Button, Card, Center, Group, Loader, Modal, Stack, Text, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { useMe } from "../../api/auth";
import ConsentPanel from "./ConsentPanel";
import EnquiriesPanel from "./EnquiriesPanel";
import GuardiansPanel from "./GuardiansPanel";
import { canMergeRecords } from "./leadApi";
import MergeDialog from "./MergeDialog";
import PatientForm from "./PatientForm";
import { mergedInto, peopleErrorKey, revealOib, usePatient, type PatientDetail } from "./api";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text>{value || "-"}</Text>
    </div>
  );
}

function OibField({ patient }: { patient: PatientDetail }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [revealed, setRevealed] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const active = useRef(false);

  useLayoutEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  async function reveal() {
    setPending(true);
    setError(null);
    try {
      const value = await revealOib(patient.id);
      if (active.current) setRevealed(value);
    } catch (error) {
      if (active.current) {
        setError(error);
        if (mergedInto(error)) void client.invalidateQueries({ queryKey: ["patient", patient.id] });
      }
    } finally {
      if (active.current) setPending(false);
    }
  }
  return (
    <div>
      <Text size="xs" c="dimmed">
        {t("people.fields.oib")}
      </Text>
      <Group gap="xs">
        <Text>{revealed ?? patient.oib_masked ?? "-"}</Text>
        {patient.oib_masked && revealed === null && (
          <Button variant="subtle" size="compact-sm" loading={pending} onClick={() => void reveal()}>
            {t("people.detail.showOib")}
          </Button>
        )}
      </Group>
      {error !== null && <Text c="red" size="sm">{t(peopleErrorKey(error))}</Text>}
    </div>
  );
}

export default function PatientDetailPage() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const location = useLocation();
  const { data: patient, dataUpdatedAt, error, isPending } = usePatient(id);
  const mergedNotice = (location.state as { merged?: boolean } | null)?.merged === true;

  const kept = mergedInto(error);
  if (kept && kept !== id) return <Navigate to={`/patients/${kept}`} replace state={{ merged: true }} />;

  if (isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (error || !patient) {
    return (
      <Stack>
        <Alert color="red">{t(peopleErrorKey(error))}</Alert>
        <Anchor component={Link} to="/patients">
          {t("people.detail.back")}
        </Anchor>
      </Stack>
    );
  }

  return <PatientRecord key={patient.id} patient={patient} revision={dataUpdatedAt} mergedNotice={mergedNotice} />;
}

function PatientRecord({ patient, revision, mergedNotice }: {
  patient: PatientDetail;
  revision: number;
  mergedNotice: boolean;
}) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const [action, setAction] = useState<"edit" | "merge" | null>(null);
  const canMerge = canMergeRecords(me);

  return (
    <Stack>
      <Anchor component={Link} to="/patients" size="sm">
        {t("people.detail.back")}
      </Anchor>
      {mergedNotice && <Alert color="blue">{t("people.detail.mergedNotice")}</Alert>}
      <Group justify="space-between">
        <Group>
          <Title order={2}>
            {patient.first_name} {patient.last_name}
          </Title>
          {patient.is_minor && <Badge color="grape">{t("people.detail.minor")}</Badge>}
        </Group>
        <Group>
          <Button variant="light" onClick={() => setAction("edit")}>{t("people.detail.edit")}</Button>
          {canMerge && (
            <Button variant="default" onClick={() => setAction("merge")}>{t("people.merge.patientTitle")}</Button>
          )}
        </Group>
      </Group>
      <Card withBorder component="section" aria-labelledby="contact-title">
        <Stack>
          <Title order={4} id="contact-title">
            {t("people.detail.contact")}
          </Title>
          <Group align="flex-start" gap="xl">
            <Field label={t("people.fields.dateOfBirth")} value={patient.date_of_birth} />
            <Field
              label={t("people.detail.age")}
              value={patient.age === null || patient.age === undefined ? null : String(patient.age)}
            />
            <Field label={t("people.fields.phone")} value={patient.phone} />
            <Field label={t("people.fields.email")} value={patient.email} />
            <OibField key={revision} patient={patient} />
          </Group>
          <Field label={t("people.fields.address")} value={patient.address} />
          <Field label={t("people.fields.notes")} value={patient.notes} />
          <Field label={t("people.fields.preferredClinic")} value={patient.preferred_clinic?.name} />
        </Stack>
      </Card>
      <GuardiansPanel patient={patient} />
      <ConsentPanel patient={patient} />
      <EnquiriesPanel patientId={patient.id} />
      {action === "edit" && (
        <Modal opened onClose={() => setAction(null)} title={t("people.detail.edit")} size="lg">
          <PatientForm patient={patient} onCancel={() => setAction(null)} onSaved={() => setAction(null)} />
        </Modal>
      )}
      {action === "merge" && canMerge && (
        <MergeDialog origin={{ kind: "patient", record: patient }} onClose={() => setAction(null)} />
      )}
    </Stack>
  );
}
