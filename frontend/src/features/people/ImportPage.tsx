import {
  Alert,
  Anchor,
  Button,
  Card,
  Checkbox,
  Group,
  Input,
  List,
  Loader,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ApiError } from "../../api/client";
import { peopleErrorKey } from "./api";
import { useCommitImport, useImportHistory, usePreviewImport, type ImportPreview } from "./importApi";

function ImportError({ error }: { error: ApiError }) {
  const { t } = useTranslation();
  const reasons = (error.body as { reasons?: unknown } | undefined)?.reasons;
  return (
    <Alert color="red">
      {t("people.imports.errors." + error.code, { defaultValue: t(peopleErrorKey(error)) })}
      {Array.isArray(reasons) && reasons.length > 0 && (
        <List size="sm">
          {reasons.filter((reason) => typeof reason === "string" && reason !== error.code).map((reason) => (
            <List.Item key={reason}>
              {t("people.imports.errors." + reason, { defaultValue: t("people.imports.errors.invalid_file") })}
            </List.Item>
          ))}
        </List>
      )}
    </Alert>
  );
}

function ImportCounts({ counts, committed = false }: { counts: ImportPreview["counts"]; committed?: boolean }) {
  const { t } = useTranslation();
  return committed
    ? t("people.imports.resultCounts", { created: counts.created ?? 0, skipped: counts.skipped ?? 0 })
    : t("people.imports.previewCounts", {
        total: counts.total ?? 0,
        valid: counts.valid ?? 0,
        invalid: counts.invalid ?? 0,
        duplicate: counts.duplicate ?? 0,
      });
}

function ImportStatus({ status }: { status: string }) {
  const { t } = useTranslation();
  return t("people.imports.statuses." + status, { defaultValue: t("people.imports.statuses.unknown") });
}

function PreviewTable({ preview }: { preview: ImportPreview }) {
  const { t } = useTranslation();
  return (
    <>
      <Title order={2} id="import-preview-title">{t("people.imports.previewTitle")}</Title>
      <Text><ImportCounts counts={preview.counts} /></Text>
      {preview.ignored_columns.length > 0 && (
        <Text size="sm" c="dimmed">
          {t("people.imports.ignoredColumns", { columns: preview.ignored_columns.join(", ") })}
        </Text>
      )}
      <ScrollArea.Autosize mah={480}>
        <Table striped aria-labelledby="import-preview-title">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("people.imports.line")}</Table.Th>
              <Table.Th>{t("people.imports.status")}</Table.Th>
              <Table.Th>{t("people.imports.details")}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {preview.rows.map((row) => (
              <Table.Tr key={row.line}>
                <Table.Td>{row.line}</Table.Td>
                <Table.Td><ImportStatus status={row.status} /></Table.Td>
                <Table.Td>
                  {row.errors.map((code) => (
                    <Text size="sm" c="red" key={code}>
                      {t("people.imports.rowErrors." + code, { defaultValue: t("people.imports.rowErrors.unknown") })}
                    </Text>
                  ))}
                  {row.duplicates.map((duplicate) => (
                    <Text size="sm" key={duplicate.kind + "-" + duplicate.id}>
                      <Anchor component={Link} to={"/" + (duplicate.kind === "patient" ? "patients" : "leads") + "/" + duplicate.id}>
                        {duplicate.display_name}
                      </Anchor>
                    </Text>
                  ))}
                  {row.in_file_duplicate_of_line !== null && (
                    <Text size="sm">{t("people.imports.duplicateLine", { line: row.in_file_duplicate_of_line })}</Text>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea.Autosize>
    </>
  );
}

function ImportHistory() {
  const { t, i18n } = useTranslation();
  const history = useImportHistory();
  const dateFormat = new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: "short", timeStyle: "short" });
  return (
    <Card withBorder component="section" aria-labelledby="import-history-title">
      <Stack>
        <Title order={2} id="import-history-title">{t("people.imports.history")}</Title>
        {history.isPending ? (
          <Loader aria-label={t("common.loading")} />
        ) : history.error ? (
          <ImportError error={history.error} />
        ) : !history.data?.items.length ? (
          <Text c="dimmed">{t("people.imports.noHistory")}</Text>
        ) : (
          <Table.ScrollContainer minWidth={580}>
            <Table striped aria-labelledby="import-history-title">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("people.imports.filename")}</Table.Th>
                  <Table.Th>{t("people.imports.status")}</Table.Th>
                  <Table.Th>{t("people.imports.createdAt")}</Table.Th>
                  <Table.Th>{t("people.imports.committedAt")}</Table.Th>
                  <Table.Th>{t("people.imports.counts")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {history.data.items.map((item) => (
                  <Table.Tr key={item.id}>
                    <Table.Td>{item.filename}</Table.Td>
                    <Table.Td><ImportStatus status={item.status} /></Table.Td>
                    <Table.Td>{dateFormat.format(new Date(item.created_at))}</Table.Td>
                    <Table.Td>{item.committed_at ? dateFormat.format(new Date(item.committed_at)) : "—"}</Table.Td>
                    <Table.Td><ImportCounts counts={item.counts} committed={item.status === "committed"} /></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>
    </Card>
  );
}

export default function ImportPage() {
  const { t } = useTranslation();
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [includeDuplicates, setIncludeDuplicates] = useState(false);
  const preview = usePreviewImport();
  const commit = useCommitImport();
  const result = commit.data;
  const busy = preview.isPending || commit.isPending;

  function resetPreview() {
    preview.reset();
    commit.reset();
    setIncludeDuplicates(false);
  }

  return (
    <Stack>
      <Title order={1}>{t("people.imports.title")}</Title>
      <Card withBorder>
        <Stack>
          <Group align="flex-end">
            <Input.Wrapper id={fileId} label={t("people.imports.file")}>
              <Input
                id={fileId}
                type="file"
                accept=".csv,text/csv"
                disabled={busy}
                onChange={(event) => {
                  setFile(event.currentTarget.files?.[0] ?? null);
                  resetPreview();
                }}
              />
            </Input.Wrapper>
            <Button
              loading={preview.isPending}
              disabled={!file || busy}
              onClick={() => {
                if (file) {
                  resetPreview();
                  preview.mutate(file);
                }
              }}
            >
              {t("people.imports.preview")}
            </Button>
          </Group>
          {preview.error && <ImportError error={preview.error} />}
          {commit.error && <ImportError error={commit.error} />}
          {result && <Alert color="green"><ImportCounts counts={result} committed /></Alert>}
          {preview.data && !result && (
            <>
              <PreviewTable preview={preview.data} />
              <Group justify="space-between">
                <Checkbox
                  label={t("people.imports.includeDuplicates")}
                  checked={includeDuplicates}
                  disabled={busy}
                  onChange={(event) => setIncludeDuplicates(event.currentTarget.checked)}
                />
                <Button
                  loading={commit.isPending}
                  disabled={commit.error?.code === "already_committed" || commit.error?.code === "import_expired"}
                  onClick={() => {
                    if (preview.data) {
                      commit.mutate({
                        importId: preview.data.import_id,
                        body: { include_duplicates: includeDuplicates },
                      });
                    }
                  }}
                >
                  {t("people.imports.commit")}
                </Button>
              </Group>
            </>
          )}
        </Stack>
      </Card>
      <ImportHistory />
    </Stack>
  );
}
