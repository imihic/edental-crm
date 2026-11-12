import { Alert, Anchor, Button, Group, Loader, NativeSelect, Pagination, Stack, Table, Tabs, Text, TextInput, Title } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useMe } from "../../api/auth";
import { peopleErrorKey } from "./api";
import { useLeads, type LeadCreated, type LeadStage } from "./leadApi";
import NewLeadDialog from "./NewLeadDialog";

const PAGE_SIZE = 25;
const STAGES = ["new", "contacted", "consultation_booked", "converted", "lost"] as const satisfies readonly LeadStage[];
type StageFilter = LeadStage | "all";

export default function LeadsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const clinics = me.data?.organization_clinics ?? [];
  const [stage, setStage] = useState<StageFilter>("all");
  const [clinicId, setClinicId] = useState("");
  const [text, setText] = useState("");
  const [q] = useDebouncedValue(text.trim(), 300);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [attachedPatientId, setAttachedPatientId] = useState<string | null>(null);
  const list = useLeads({ stage: stage === "all" ? null : stage, q, clinic_id: clinicId, page, page_size: PAGE_SIZE });
  const counts = list.data?.counts;
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE));

  function created(result: LeadCreated) {
    setCreating(false);
    if (result.attached_to === "patient" && result.patient_id) {
      setAttachedPatientId(result.patient_id);
    } else if (result.attached_to === "lead" && result.lead_id) {
      navigate(`/leads/${result.lead_id}`);
    }
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{t("people.leads.title")}</Title>
        <Button onClick={() => { setAttachedPatientId(null); setCreating(true); }}>{t("people.leads.new")}</Button>
      </Group>
      {attachedPatientId && (
        <Alert color="green" role="status">
          <Group gap="xs">
            <Text>{t("people.leads.attached")}</Text>
            <Anchor component={Link} to={`/patients/${attachedPatientId}`}>{t("people.leads.openPatient")}</Anchor>
          </Group>
        </Alert>
      )}
      <Group grow align="flex-end">
        <TextInput
          type="search" maxLength={100}
          aria-label={t("people.leads.search")} placeholder={t("people.leads.search")}
          value={text}
          onChange={(e) => { setText(e.currentTarget.value); setPage(1); }}
        />
        <NativeSelect
          label={t("people.enquiries.clinic")} value={clinicId}
          onChange={(e) => { setClinicId(e.currentTarget.value); setPage(1); }}
          data={[{ value: "", label: t("people.leads.allClinics") }, ...clinics.map((c) => ({ value: c.id, label: c.name }))]}
        />
      </Group>
      <Tabs value={stage} onChange={(value) => { setStage(value as StageFilter); setPage(1); }}>
        <Tabs.List aria-label={t("people.leads.stage")}>
          <Tabs.Tab value="all">
            {t("people.leads.all")}{counts && ` (${STAGES.reduce((total, key) => total + (counts[key] ?? 0), 0)})`}
          </Tabs.Tab>
          {STAGES.map((key) => (
            <Tabs.Tab key={key} value={key}>
              {t(`people.leads.stages.${key}`)}{counts && ` (${counts[key] ?? 0})`}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        <Tabs.Panel value={stage} pt="md">
          {list.error && <Alert color="red">{t(peopleErrorKey(list.error))}</Alert>}
          {(list.isPending || list.isPlaceholderData) && <Loader size="sm" aria-label={t("common.loading")} />}
          {list.data && !list.isPlaceholderData && (
            <Stack>
              {list.data.items.length === 0 ? <Text c="dimmed">{t("people.leads.empty")}</Text> : (
                <Table.ScrollContainer minWidth={600}>
                  <Table striped>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t("people.fields.fullName")}</Table.Th>
                        <Table.Th>{t("people.leads.stage")}</Table.Th>
                        <Table.Th>{t("people.fields.phone")}</Table.Th>
                        <Table.Th>{t("people.fields.email")}</Table.Th>
                        <Table.Th>{t("people.enquiries.clinic")}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {list.data.items.map((lead) => (
                        <Table.Tr key={lead.id}>
                          <Table.Td>
                            <Anchor component={Link} to={`/leads/${lead.id}`}>{lead.full_name}</Anchor>
                          </Table.Td>
                          <Table.Td>{t(`people.leads.stages.${lead.stage}`)}</Table.Td>
                          <Table.Td>{lead.phone}</Table.Td>
                          <Table.Td>{lead.email}</Table.Td>
                          <Table.Td>{clinics.find((clinic) => clinic.id === lead.clinic_id)?.name}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
              {pages > 1 && <Pagination total={pages} value={Math.min(page, pages)} onChange={setPage} />}
            </Stack>
          )}
        </Tabs.Panel>
      </Tabs>
      {creating && (
        <NewLeadDialog
          clinics={clinics}
          clinicId={clinicId || me.data?.clinics[0]?.id || ""}
          onCreated={created}
          onClose={() => setCreating(false)}
        />
      )}
    </Stack>
  );
}
