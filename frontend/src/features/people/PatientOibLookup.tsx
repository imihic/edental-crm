import { Alert, Button, Group, Modal, Stack, TextInput } from "@mantine/core";
import { useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { lookupPatientByOib, peopleErrorKey } from "./api";
import { isValidOib } from "./schemas";

export default function PatientOibLookup({ onClose, onFound }: {
  onClose: () => void;
  onFound: (patientId: string) => void;
}) {
  const { t } = useTranslation();
  const [oib, setOib] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useLayoutEffect(() => () => request.current?.abort(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (request.current) return;
    const exactOib = oib.trim();
    if (!isValidOib(exactOib)) {
      setMessage("people.validation.oibInvalid");
      return;
    }

    const controller = new AbortController();
    request.current = controller;
    setMessage(null);
    setPending(true);
    try {
      const patientId = await lookupPatientByOib(exactOib, controller.signal);
      if (controller.signal.aborted) return;
      if (patientId) onFound(patientId);
      else setMessage("people.patients.oibNoMatch");
    } catch (error) {
      if (!controller.signal.aborted) setMessage(peopleErrorKey(error));
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return (
    <Modal opened onClose={onClose} title={t("people.patients.lookupOib")}>
      <form onSubmit={submit} noValidate>
        <Stack>
          {message && <Alert color={message === "people.patients.oibNoMatch" ? "blue" : "red"}>{t(message)}</Alert>}
          <TextInput
            label={t("people.fields.oib")}
            value={oib}
            onChange={(event) => {
              setOib(event.currentTarget.value);
              setMessage(null);
            }}
            inputMode="numeric"
            autoComplete="off"
            disabled={pending}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t("common.cancel")}</Button>
            <Button type="submit" loading={pending}>{t("people.patients.findPatient")}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
