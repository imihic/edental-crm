import { Alert, Button, Group, Loader, Modal, Pagination, Radio, Stack, Table, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { peopleErrorKey, usePatient, usePatients, type PatientDetail } from "./api";
import { peopleActionErrorKey, type LeadDetail } from "./leadApi";

type MergeBody = components["schemas"]["MergeIn"];
type MergeOrigin = { kind: "patient"; record: PatientDetail } | { kind: "lead"; record: LeadDetail };
type Choices = MergeBody["field_choices"];
const PAGE_SIZE = 25;

const FIELD_LABELS = {
  first_name: "firstName",
  last_name: "lastName",
  date_of_birth: "dateOfBirth",
  phone: "phone",
  email: "email",
  oib: "oib",
  address: "address",
  notes: "notes",
  preferred_clinic_id: "preferredClinic",
  preferred_language: "preferredLanguage",
} as const;
type Field = keyof typeof FIELD_LABELS;

function patientValues(patient: PatientDetail): Record<Field, string | null> {
  return {
    first_name: patient.first_name,
    last_name: patient.last_name,
    date_of_birth: patient.date_of_birth,
    phone: patient.phone,
    email: patient.email,
    oib: patient.oib_masked,
    address: patient.address,
    notes: patient.notes,
    preferred_clinic_id: patient.preferred_clinic?.id ?? null,
    preferred_language: patient.preferred_language,
  };
}

export default function MergeDialog({ origin, onClose }: { origin: MergeOrigin; onClose: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search.trim(), 300);
  const [page, setPage] = useState(1);
  const list = usePatients({ q, page, page_size: PAGE_SIZE }, selected === null);
  const candidates = list.data?.items.filter((patient) => origin.kind !== "patient" || patient.id !== origin.record.id);
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE));
  const merge = useMutation({
    mutationFn: ({ keptId, body }: { keptId: string; body: MergeBody }) =>
      apiFetch<PatientDetail>(`/api/patients/${keptId}/merge`, { method: "POST", body }),
    onSuccess: (patient, { body }) => {
      client.setQueryData(["patient", patient.id], patient);
      client.removeQueries({ queryKey: [body.retired_kind, body.retired_id] });
      void client.invalidateQueries({ queryKey: ["patient", patient.id, "consents"] });
      void client.invalidateQueries({ queryKey: ["patient", patient.id, "enquiries"] });
      void client.invalidateQueries({ queryKey: ["patients"] });
      void client.invalidateQueries({ queryKey: ["leads"] });
    },
  });

  return (
    <Modal opened size="xl" onClose={onClose}
      title={t(origin.kind === "patient" ? "people.merge.patientTitle" : "people.merge.leadTitle")}
      closeOnEscape={!merge.isPending} closeOnClickOutside={!merge.isPending} withCloseButton={!merge.isPending}>
      {selected === null ? (
        <Stack>
          <Text>{t("people.merge.choosePatient")}</Text>
          <TextInput type="search" maxLength={100} label={t("people.patients.search")} value={search}
            onChange={(e) => { setSearch(e.currentTarget.value); setPage(1); }} />
          {list.error && <Alert color="red">{t(peopleErrorKey(list.error))}</Alert>}
          {list.isPending || list.isPlaceholderData || search.trim() !== q ? (
            <Loader size="sm" aria-label={t("common.loading")} />
          ) : (
            <>
              {candidates?.length === 0 && <Text c="dimmed">{t("people.merge.noMatches")}</Text>}
              {candidates?.map((candidate) => (
                <Button key={candidate.id} variant="light" onClick={() => setSelected(candidate.id)}>
                  {candidate.first_name} {candidate.last_name}
                </Button>
              ))}
              {pages > 1 && <Pagination total={pages} value={Math.min(page, pages)} onChange={setPage} />}
            </>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t("common.cancel")}</Button>
          </Group>
        </Stack>
      ) : (
        <MergeReview
          key={selected}
          origin={origin}
          patientId={selected}
          busy={merge.isPending}
          error={merge.error}
          onBack={() => { merge.reset(); setSelected(null); }}
          onMerge={(keptId, body) => merge.mutate({ keptId, body }, {
            onSuccess: (patient) => {
              onClose();
              navigate(`/patients/${patient.id}`, { replace: true });
            },
          })}
        />
      )}
    </Modal>
  );
}

function MergeReview({ origin, patientId, busy, error, onBack, onMerge }: {
  origin: MergeOrigin;
  patientId: string;
  busy: boolean;
  error: unknown;
  onBack: () => void;
  onMerge: (keptId: string, body: MergeBody) => void;
}) {
  const { t } = useTranslation();
  const { data: selected, isPending, error: loadError } = usePatient(patientId);
  const [choices, setChoices] = useState<Choices>({});
  const [confirming, setConfirming] = useState(false);

  if (isPending) return <Loader size="sm" aria-label={t("common.loading")} />;
  if (loadError || !selected) {
    return (
      <Stack>
        <Alert color="red">{t(peopleErrorKey(loadError))}</Alert>
        <Button variant="default" onClick={onBack}>{t("people.merge.back")}</Button>
      </Stack>
    );
  }

  const kept = origin.kind === "patient" ? origin.record : selected;
  const retired = origin.kind === "patient" ? selected : origin.record;
  const keptName = `${kept.first_name} ${kept.last_name}`;
  const retiredName = "full_name" in retired ? retired.full_name : `${retired.first_name} ${retired.last_name}`;
  const keptValues = patientValues(kept);
  const retiredValues: Partial<Record<Field, string | null>> = origin.kind === "patient"
    ? patientValues(selected)
    : { phone: origin.record.phone, email: origin.record.email };
  const fields = (Object.keys(retiredValues) as Field[]).map((field) => {
    const left = keptValues[field];
    const right = retiredValues[field] ?? null;
    const differs = left !== right || (field === "oib" && left !== null && right !== null);
    return { field, left, right, differs };
  });

  function confirm() {
    const fieldChoices: Choices = {};
    for (const { field, differs } of fields) {
      if (differs) fieldChoices[field] = choices[field] ?? "kept";
    }
    onMerge(kept.id, { retired_kind: origin.kind, retired_id: retired.id, field_choices: fieldChoices });
  }

  function display(field: Field, value: string | null, record: PatientDetail | LeadDetail) {
    if (!value) return "—";
    if (field === "preferred_clinic_id" && "preferred_clinic" in record) return record.preferred_clinic?.name ?? "—";
    if (field === "preferred_language") return t(`people.languages.${value}`, { defaultValue: value });
    return value;
  }

  if (confirming) {
    return (
      <Stack>
        <Alert color="orange">{t("people.merge.confirmation", { kept: keptName, retired: retiredName })}</Alert>
        {error != null && <Alert color="red">{t(peopleActionErrorKey(error))}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" disabled={busy} onClick={() => setConfirming(false)}>{t("people.merge.back")}</Button>
          <Button color="red" loading={busy} onClick={confirm}>{t("people.merge.confirm")}</Button>
        </Group>
      </Stack>
    );
  }

  return (
    <Stack>
      {!fields.some(({ differs }) => differs) && <Text c="dimmed">{t("people.merge.noDifferences")}</Text>}
      <Table.ScrollContainer minWidth={420}>
        <Table withTableBorder withRowBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("people.merge.field")}</Table.Th>
              <Table.Th>{t("people.merge.kept")}<br />{keptName}</Table.Th>
              <Table.Th>{t("people.merge.retired")}<br />{retiredName}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {fields.map(({ field, left, right, differs }) => {
              const label = t(`people.fields.${FIELD_LABELS[field]}`);
              const side = choices[field] ?? "kept";
              return (
                <Table.Tr key={field}>
                  <Table.Th scope="row">{label}</Table.Th>
                  {([
                    { key: "kept", value: left, record: kept, name: keptName },
                    { key: "retired", value: right, record: retired, name: retiredName },
                  ] as const).map(({ key, value, record, name }) => (
                    <Table.Td key={key}>
                      {differs ? (
                        <Radio
                          name={`merge-${field}`}
                          aria-label={t("people.merge.fieldFrom", {
                            field: label, name: keptName === retiredName ? `${name} (${t(`people.merge.${key}`)})` : name,
                          })}
                          label={display(field, value, record)}
                          checked={side === key}
                          onChange={() => setChoices((previous) => ({ ...previous, [field]: key }))}
                        />
                      ) : display(field, value, record)}
                    </Table.Td>
                  ))}
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {fields.some(({ field, left, right }) => field === "oib" && (left || right)) && (
        <Text size="sm" c="dimmed">{t("people.merge.maskedOib")}</Text>
      )}
      <Group justify="flex-end">
        <Button variant="default" onClick={onBack}>{t("people.merge.back")}</Button>
        <Button onClick={() => setConfirming(true)}>{t("people.merge.continue")}</Button>
      </Group>
    </Stack>
  );
}
