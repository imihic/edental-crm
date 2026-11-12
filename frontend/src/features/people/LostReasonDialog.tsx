import { Alert, Button, Group, Modal, NativeSelect, Stack, Textarea } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { peopleActionErrorKey, type LostReason } from "./leadApi";

const REASONS = ["price", "distance", "chose_other_clinic", "no_response", "not_needed", "other"] as const satisfies readonly LostReason[];

export default function LostReasonDialog({ onClose, onSubmit, busy, error }: {
  onClose: () => void;
  onSubmit: (reason: LostReason, note: string | null) => void;
  busy: boolean;
  error: unknown;
}) {
  const { t } = useTranslation();
  const [reason, setReason] = useState<LostReason | "">("");
  const [note, setNote] = useState("");
  const [missingReason, setMissingReason] = useState(false);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!reason) {
      setMissingReason(true);
      return;
    }
    onSubmit(reason, note.trim() || null);
  }

  return (
    <Modal opened onClose={onClose} title={t("people.lost.title")}
      closeOnEscape={!busy} closeOnClickOutside={!busy} withCloseButton={!busy}>
      <form onSubmit={submit} noValidate>
        <Stack>
          {error != null && <Alert color="red">{t(peopleActionErrorKey(error))}</Alert>}
          <NativeSelect
            required label={t("people.lost.reason")} value={reason}
            onChange={(e) => { setReason(e.currentTarget.value as LostReason | ""); setMissingReason(false); }}
            error={missingReason ? t("people.lost.required") : undefined}
            data={[
              { value: "", label: t("people.lost.choose") },
              ...REASONS.map((value) => ({ value, label: t(`people.lost.reasons.${value}`) })),
            ]}
          />
          <Textarea label={t("people.fields.notes")} value={note} maxLength={500}
            onChange={(e) => setNote(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} disabled={busy}>{t("common.cancel")}</Button>
            <Button type="submit" loading={busy}>{t("common.save")}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
