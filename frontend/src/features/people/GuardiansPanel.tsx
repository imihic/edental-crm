import {
  Alert,
  Anchor,
  Button,
  Card,
  Group,
  List,
  Modal,
  NativeSelect,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDebouncedValue } from "@mantine/hooks";
import { zod4Resolver as zodResolver } from "mantine-form-zod-resolver";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  peopleErrorKey,
  useAddGuardian,
  usePatients,
  useRemoveGuardian,
  type GuardianInput,
  type PatientDetail,
  type PatientSummary,
} from "./api";
import { contactSchema, isValidOib } from "./schemas";

type Relationship = GuardianInput["relationship"];
const RELATIONSHIPS: Relationship[] = ["parent", "legal_guardian", "other"];

function PatientPicker({ excludeId, onPick }: { excludeId: string; onPick: (patient: PatientSummary | null) => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [q] = useDebouncedValue(text.trim(), 300);
  const ready = q !== "" && q === text.trim() && !isValidOib(q);
  const list = usePatients({ q, page: 1, page_size: 10 }, ready);
  const items = ready ? (list.data?.items ?? []).filter((p) => p.id !== excludeId) : [];
  return (
    <Stack gap="xs">
      <TextInput
        type="search"
        label={t("people.guardians.searchPatient")}
        value={text}
        maxLength={100}
        onChange={(e) => {
          onPick(null);
          setText(e.currentTarget.value);
        }}
      />
      {ready && list.isSuccess && items.length === 0 && <Text c="dimmed">{t("people.patients.empty")}</Text>}
      {ready && (
        <List listStyleType="none" spacing={4}>
          {items.map((p) => (
            <List.Item key={p.id}>
              <Button variant="subtle" size="compact-sm" onClick={() => onPick(p)}>
                {p.first_name} {p.last_name}
                {p.date_of_birth ? ` (${p.date_of_birth})` : ""}
              </Button>
            </List.Item>
          ))}
        </List>
      )}
    </Stack>
  );
}

function AddGuardianDialog({ patient, onClose }: { patient: PatientDetail; onClose: () => void }) {
  const { t } = useTranslation();
  const add = useAddGuardian(patient.id);
  const [mode, setMode] = useState<"patient" | "contact">("patient");
  const [relationship, setRelationship] = useState<Relationship>("parent");
  const [picked, setPicked] = useState<PatientSummary | null>(null);
  const form = useForm({
    initialValues: { full_name: "", phone: "", email: "" },
    validate: zodResolver(contactSchema, { errorPriority: "first" }),
  });
  const tr = (msg: unknown) => (typeof msg === "string" ? t(msg) : undefined);

  const submit = (body: GuardianInput) => add.mutate(body, { onSuccess: onClose });

  return (
    <Modal opened onClose={onClose} title={t("people.guardians.add")}>
      <Stack>
        {add.error && <Alert color="red">{t(peopleErrorKey(add.error))}</Alert>}
        <SegmentedControl
          value={mode}
          disabled={add.isPending}
          onChange={(v) => {
            setPicked(null);
            setMode(v as "patient" | "contact");
          }}
          data={[
            { value: "patient", label: t("people.guardians.existingPatient") },
            { value: "contact", label: t("people.guardians.newContact") },
          ]}
        />
        <NativeSelect
          label={t("people.guardians.relationship")}
          value={relationship}
          onChange={(e) => setRelationship(e.currentTarget.value as Relationship)}
          data={RELATIONSHIPS.map((r) => ({ value: r, label: t(`people.guardians.relationships.${r}`) }))}
        />
        {mode === "patient" ? (
          <>
            <PatientPicker excludeId={patient.id} onPick={setPicked} />
            {picked && (
              <Text size="sm">
                {t("people.guardians.picked")} {picked.first_name} {picked.last_name}
                {picked.date_of_birth ? ` (${picked.date_of_birth})` : ""}
              </Text>
            )}
            <Group justify="flex-end">
              <Button
                disabled={!picked}
                loading={add.isPending}
                onClick={() => picked && submit({ relationship, guardian_patient_id: picked.id })}
              >
                {t("common.add")}
              </Button>
            </Group>
          </>
        ) : (
          <form
            noValidate
            onSubmit={form.onSubmit((v) =>
              submit({
                relationship,
                contact: {
                  full_name: v.full_name,
                  ...(v.phone ? { phone: v.phone } : {}),
                  ...(v.email ? { email: v.email } : {}),
                },
              }),
            )}
          >
            <Stack>
              <TextInput
                label={t("people.fields.fullName")}
                aria-required
                {...form.getInputProps("full_name")}
                error={tr(form.errors.full_name)}
              />
              <TextInput label={t("people.fields.phone")} {...form.getInputProps("phone")} error={tr(form.errors.phone)} />
              <TextInput label={t("people.fields.email")} {...form.getInputProps("email")} error={tr(form.errors.email)} />
              <Group justify="flex-end">
                <Button type="submit" loading={add.isPending}>
                  {t("common.add")}
                </Button>
              </Group>
            </Stack>
          </form>
        )}
      </Stack>
    </Modal>
  );
}

export default function GuardiansPanel({ patient }: { patient: PatientDetail }) {
  const { t } = useTranslation();
  const remove = useRemoveGuardian(patient.id);
  const [adding, setAdding] = useState(false);

  return (
    <Card withBorder component="section" aria-labelledby="guardians-title">
      <Stack>
        <Group justify="space-between">
          <Title order={4} id="guardians-title">
            {t("people.guardians.title")}
          </Title>
          <Button variant="light" size="compact-md" onClick={() => setAdding(true)}>
            {t("people.guardians.add")}
          </Button>
        </Group>
        {patient.is_minor && patient.guardians.length === 0 && (
          <Alert color="yellow">{t("people.guardians.minorNeedsGuardian")}</Alert>
        )}
        {remove.error && <Alert color="red">{t(peopleErrorKey(remove.error))}</Alert>}
        {patient.guardians.length === 0 ? (
          <Text c="dimmed">{t("people.guardians.none")}</Text>
        ) : (
          <List spacing="xs" listStyleType="none">
            {patient.guardians.map((g) => (
              <List.Item key={g.id}>
                <Group justify="space-between" wrap="nowrap">
                  <Text>
                    {g.kind === "patient" ? (
                      <Anchor component={Link} to={`/patients/${g.guardian_id}`}>
                        {g.display_name}
                      </Anchor>
                    ) : (
                      g.display_name
                    )}{" "}
                    <Text span c="dimmed" size="sm">
                      ({t(`people.guardians.relationships.${g.relationship}`)}
                      {g.phone ? `, ${g.phone}` : ""}
                      {g.email ? `, ${g.email}` : ""})
                    </Text>
                  </Text>
                  <Button
                    variant="subtle"
                    color="red"
                    size="compact-sm"
                    aria-label={`${t("people.guardians.remove")}: ${g.display_name}`}
                    loading={remove.isPending && remove.variables === g.id}
                    onClick={() => remove.mutate(g.id)}
                  >
                    {t("people.guardians.remove")}
                  </Button>
                </Group>
              </List.Item>
            ))}
          </List>
        )}
        {patient.guardian_of.length > 0 && (
          <>
            <Title order={5}>{t("people.guardians.guardianOf")}</Title>
            <List>
              {patient.guardian_of.map((g) => (
                <List.Item key={g.patient_id}>
                  <Anchor component={Link} to={`/patients/${g.patient_id}`}>
                    {g.display_name}
                  </Anchor>
                </List.Item>
              ))}
            </List>
          </>
        )}
      </Stack>
      {adding && <AddGuardianDialog patient={patient} onClose={() => setAdding(false)} />}
    </Card>
  );
}
