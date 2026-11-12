import { Anchor, Button, Group, List, Modal, Stack, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Duplicate } from "./api";

export function DuplicateRecords({ duplicates }: { duplicates: Duplicate[] }) {
  const { t } = useTranslation();
  return (
    <List spacing="xs">
      {duplicates.map((d) => (
        <List.Item key={`${d.kind}-${d.id}`}>
          <Anchor component={Link} to={d.kind === "patient" ? `/patients/${d.id}` : `/leads/${d.id}`}>
            {d.display_name}
          </Anchor>{" "}
          <Text span c="dimmed" size="sm">
            ({t(`people.duplicates.kind.${d.kind}`)}:{" "}
            {d.reasons.map((r) => t(`people.duplicates.reasons.${r}`, { defaultValue: r })).join(", ")})
          </Text>
        </List.Item>
      ))}
    </List>
  );
}

export default function DuplicateWarningDialog({
  duplicates,
  busy,
  actionLabel,
  onCreateAnyway,
  onClose,
}: {
  duplicates: Duplicate[];
  busy: boolean;
  actionLabel?: string;
  onCreateAnyway: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Modal opened onClose={onClose} title={t("people.duplicates.title")} zIndex={400}
      closeOnEscape={!busy} closeOnClickOutside={!busy} withCloseButton={!busy}>
      <Stack>
        <Text>{t("people.duplicates.description")}</Text>
        <DuplicateRecords duplicates={duplicates} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button color="red" loading={busy} onClick={onCreateAnyway}>
            {actionLabel ?? t("people.duplicates.createAnyway")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
