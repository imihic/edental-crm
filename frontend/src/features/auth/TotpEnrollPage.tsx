import { Alert, Button, Code, Container, Group, Loader, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { zod4Resolver as zodResolver } from "mantine-form-zod-resolver";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { errorKey, useConfirmTotp, useEnrollTotp, type Me } from "../../api/auth";
import SessionControls from "../shell/SessionControls";
import { codeSchema } from "./schemas";

export function manualEntryKey(otpauthUri: string): string {
  const secret = /[?&]secret=([^&]*)/i.exec(otpauthUri)?.[1] ?? "";
  return (decodeURIComponent(secret).toUpperCase().match(/.{1,4}/g) ?? []).join(" ");
}

export default function TotpEnrollPage({ me }: { me: Me }) {
  const { t } = useTranslation();
  const { mutate: startEnroll, data, error: enrollError } = useEnrollTotp();
  const confirm = useConfirmTotp();
  const form = useForm({ initialValues: { code: "" }, validate: zodResolver(codeSchema, { errorPriority: "first" }) });
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    startEnroll();
  }, [startEnroll]);

  const manualKey = data ? manualEntryKey(data.otpauth_uri) : "";

  return (
    <>
      <Group component="header" justify="flex-end" p="md" wrap="wrap">
        <SessionControls me={me} />
      </Group>
      <Container size="xs" py="xl">
        <form onSubmit={form.onSubmit((v) => confirm.mutate(v))} noValidate>
          <Stack>
            <Title order={2}>{t("auth.enroll.title")}</Title>
            <Text c="dimmed">{t("auth.enroll.description")}</Text>
            {enrollError && <Alert color="red">{t(errorKey(enrollError))}</Alert>}
            {confirm.error && <Alert color="red">{t(errorKey(confirm.error))}</Alert>}
            {data ? (
              <>
                <QRCodeSVG value={data.otpauth_uri} size={192} role="img" aria-label={t("auth.enroll.qrLabel")} />
                {manualKey && (
                  <Stack gap={4}>
                    <Text size="sm">{t("auth.enroll.manualEntry")}</Text>
                    <Code block>{manualKey}</Code>
                  </Stack>
                )}
              </>
            ) : (
              !enrollError && <Loader />
            )}
            <TextInput
              label={t("auth.enroll.code")}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              {...form.getInputProps("code")}
              error={typeof form.errors.code === "string" ? t(form.errors.code) : undefined}
            />
            <Button type="submit" loading={confirm.isPending} disabled={!data}>
              {t("auth.enroll.submit")}
            </Button>
          </Stack>
        </form>
      </Container>
    </>
  );
}
