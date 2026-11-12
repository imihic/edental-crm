import { Alert, Button, Group, Modal, Pagination, Stack, Table, Text, TextInput, Title, Anchor } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { peopleErrorKey, usePatients } from "./api";
import PatientForm from "./PatientForm";
import PatientOibLookup from "./PatientOibLookup";
import { isValidOib } from "./schemas";

const PAGE_SIZE = 25;

function searchText(value: string) {
  const query = value.trim().slice(0, 100);
  return isValidOib(query) ? "" : query;
}

export default function PatientsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const rawQuery = params.get("q") ?? "";
  const q = searchText(rawQuery);
  const requestedPage = Number(params.get("page"));
  const page = Number.isInteger(requestedPage) && requestedPage >= 1 && requestedPage <= 10_000 ? requestedPage : 1;
  const [text, setText] = useState(q);
  const [debounced] = useDebouncedValue(text, 300);
  const [creating, setCreating] = useState(false);
  const [lookingUpOib, setLookingUpOib] = useState(false);
  const list = usePatients({ q, page, page_size: PAGE_SIZE });

  useEffect(() => {
    const next = searchText(debounced);
    if (next === rawQuery) return;
    setParams(
      (prev) => {
        const sp = new URLSearchParams(prev);
        if (next) sp.set("q", next);
        else sp.delete("q");
        sp.delete("page");
        return sp;
      },
      { replace: true },
    );
  }, [debounced]);

  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE));

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{t("people.patients.title")}</Title>
        <Group>
          <Button variant="default" onClick={() => setLookingUpOib(true)}>{t("people.patients.lookupOib")}</Button>
          <Button onClick={() => setCreating(true)}>{t("people.patients.new")}</Button>
        </Group>
      </Group>
      <TextInput
        type="search"
        aria-label={t("people.patients.search")}
        placeholder={t("people.patients.search")}
        value={text}
        maxLength={100}
        onChange={(e) => setText(e.currentTarget.value)}
      />
      {list.isPending && <Text c="dimmed">{t("common.loading")}</Text>}
      {list.error && <Alert color="red">{t(peopleErrorKey(list.error))}</Alert>}
      {list.data && list.data.items.length === 0 && <Text c="dimmed">{t("people.patients.empty")}</Text>}
      {list.data && list.data.items.length > 0 && (
        <Table.ScrollContainer minWidth={600}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("people.patients.name")}</Table.Th>
                <Table.Th>{t("people.fields.dateOfBirth")}</Table.Th>
                <Table.Th>{t("people.fields.phone")}</Table.Th>
                <Table.Th>{t("people.fields.email")}</Table.Th>
                <Table.Th>{t("people.fields.oib")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.data.items.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>
                    <Anchor component={Link} to={`/patients/${p.id}`}>
                      {p.first_name} {p.last_name}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>{p.date_of_birth ?? ""}</Table.Td>
                  <Table.Td>{p.phone ?? ""}</Table.Td>
                  <Table.Td>{p.email ?? ""}</Table.Td>
                  <Table.Td>{p.oib_masked ?? ""}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {pages > 1 && (
        <Pagination
          total={pages}
          value={Math.min(page, pages)}
          onChange={(p) =>
            setParams((prev) => {
              const sp = new URLSearchParams(prev);
              if (p > 1) sp.set("page", String(p));
              else sp.delete("page");
              return sp;
            })
          }
        />
      )}
      {lookingUpOib && (
        <PatientOibLookup
          onClose={() => setLookingUpOib(false)}
          onFound={(patientId) => {
            setLookingUpOib(false);
            navigate(`/patients/${patientId}`);
          }}
        />
      )}
      <Modal opened={creating} onClose={() => setCreating(false)} title={t("people.patients.new")} size="lg">
        {creating && <PatientForm
          onCancel={() => setCreating(false)}
          onSaved={(p) => {
            setCreating(false);
            navigate(`/patients/${p.id}`);
          }}
        />}
      </Modal>
    </Stack>
  );
}
