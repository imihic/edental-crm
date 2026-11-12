import { Alert, Anchor, Badge, Button, Card, Center, Group, Loader, NativeSelect, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useParams } from "react-router-dom";
import { useMe } from "../../api/auth";
import { mergedInto, peopleErrorKey } from "./api";
import { LeadConsentPanel } from "./ConsentPanel";
import ConvertLeadDialog from "./ConvertLeadDialog";
import { DuplicateRecords } from "./DuplicateWarningDialog";
import { canMergeRecords, peopleActionErrorKey, useChangeLeadStage, useLead, type LeadDetail, type LeadStage } from "./leadApi";
import LostReasonDialog from "./LostReasonDialog";
import MergeDialog from "./MergeDialog";

const ALLOWED: Record<LeadStage, readonly LeadStage[]> = {
  new: ["contacted", "consultation_booked", "lost"],
  contacted: ["consultation_booked", "lost"],
  consultation_booked: ["contacted", "lost"],
  lost: ["new"],
  converted: [],
};

export default function LeadDetailPage() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const { data: lead, error, isPending } = useLead(id);

  const kept = mergedInto(error);
  if (kept) return <Navigate to={`/patients/${kept}`} replace state={{ merged: true }} />;
  if (isPending) return <Center py="xl"><Loader aria-label={t("common.loading")} /></Center>;
  return (
    <Stack>
      <Anchor component={Link} to="/leads" size="sm">{t("people.leads.back")}</Anchor>
      {error || !lead
        ? <Alert color="red">{t(peopleErrorKey(error))}</Alert>
        : <LeadRecord key={lead.id} lead={lead} />}
    </Stack>
  );
}

function LeadRecord({ lead }: { lead: LeadDetail }) {
  const { t, i18n } = useTranslation();
  const { data: me } = useMe();
  const change = useChangeLeadStage(lead.id);
  const [action, setAction] = useState<"lost" | "convert" | "merge" | null>(null);
  const allowed = ALLOWED[lead.stage];
  const clinic = me?.organization_clinics.find((clinic) => clinic.id === lead.clinic_id);
  const canMerge = canMergeRecords(me);

  function changeStage(value: LeadStage) {
    if (!allowed.includes(value) || change.isPending) return;
    if (value === "lost") {
      change.reset();
      setAction("lost");
    } else {
      change.mutate({ stage: value });
    }
  }

  return (
    <>
      <Group justify="space-between">
        <Group>
          <Title order={2}>{lead.full_name}</Title>
          <Badge>{t(`people.leads.stages.${lead.stage}`)}</Badge>
        </Group>
        <Group>
          {lead.stage !== "converted" && (
            <Button variant="light" disabled={change.isPending} onClick={() => setAction("convert")}>
              {t("people.conversion.title")}
            </Button>
          )}
          {canMerge && (
            <Button variant="default" disabled={change.isPending} onClick={() => setAction("merge")}>
              {t("people.merge.leadTitle")}
            </Button>
          )}
        </Group>
      </Group>
      {lead.converted_patient_id && (
        <Anchor component={Link} to={`/patients/${lead.converted_patient_id}`}>{t("people.leads.openPatient")}</Anchor>
      )}
      {change.error && action !== "lost" && <Alert color="red">{t(peopleActionErrorKey(change.error))}</Alert>}
      {allowed.length > 0 && (
        <Group>
          <NativeSelect
            label={t("people.leads.changeStage")} value="" disabled={change.isPending}
            onChange={(e) => changeStage(e.currentTarget.value as LeadStage)}
            data={[
              { value: "", label: t("people.leads.chooseStage"), disabled: true },
              ...allowed.map((value) => ({ value, label: t(`people.leads.stages.${value}`) })),
            ]}
          />
        </Group>
      )}
      <Card withBorder component="section" aria-labelledby="lead-contact-title">
        <Stack>
          <Title order={4} id="lead-contact-title">{t("people.detail.contact")}</Title>
          <Group gap="xl">
            {clinic && <Text>{t("people.enquiries.clinic")}: {clinic.name}</Text>}
            <Text>{t("people.fields.phone")}: {lead.phone ?? "—"}</Text>
            <Text>{t("people.fields.email")}: {lead.email ?? "—"}</Text>
          </Group>
          {lead.lost_reason && <Text>{t("people.lost.reason")}: {t(`people.lost.reasons.${lead.lost_reason}`)}</Text>}
          {lead.lost_note && <Text style={{ whiteSpace: "pre-wrap" }}>{lead.lost_note}</Text>}
        </Stack>
      </Card>
      <Card withBorder component="section" aria-labelledby="lead-enquiries-title">
        <Stack>
          <Title order={4} id="lead-enquiries-title">{t("people.enquiries.title")}</Title>
          {lead.enquiries.length === 0 && <Text c="dimmed">{t("people.enquiries.empty")}</Text>}
          {lead.enquiries.map((enquiry) => (
            <div key={enquiry.id}>
              <Text c="dimmed" size="sm">
                {t(`people.enquiries.sources.${enquiry.source}`)} · {new Date(enquiry.received_at).toLocaleString(i18n.language)}
              </Text>
              <Text style={{ whiteSpace: "pre-wrap" }}>{enquiry.message}</Text>
              {enquiry.preferred_contact_time && (
                <Text size="sm">{t("people.enquiries.preferredContactTime")}: {enquiry.preferred_contact_time}</Text>
              )}
            </div>
          ))}
        </Stack>
      </Card>
      <LeadConsentPanel lead={lead} />
      {lead.possible_duplicates.length > 0 && (
        <Card withBorder component="section" aria-labelledby="lead-duplicates-title">
          <Title order={4} id="lead-duplicates-title">{t("people.duplicates.title")}</Title>
          <DuplicateRecords duplicates={lead.possible_duplicates} />
        </Card>
      )}
      {action === "lost" && allowed.includes("lost") && (
        <LostReasonDialog busy={change.isPending} error={change.error}
          onClose={() => { change.reset(); setAction(null); }}
          onSubmit={(reason, note) => change.mutate(
            { stage: "lost", lost_reason: reason, lost_note: note },
            { onSuccess: () => setAction(null) },
          )}
        />
      )}
      {action === "convert" && lead.stage !== "converted" && <ConvertLeadDialog lead={lead} onClose={() => setAction(null)} />}
      {action === "merge" && canMerge && <MergeDialog origin={{ kind: "lead", record: lead }} onClose={() => setAction(null)} />}
    </>
  );
}
