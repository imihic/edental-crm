import {
  Alert,
  Button,
  Container,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { zod4Resolver as zodResolver } from "mantine-form-zod-resolver";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  errorKey,
  useLogin,
  useVerifyTotp,
  type LoginResult,
  type OrganizationOut,
} from "../../api/auth";
import ChooseOrganizationPage from "./ChooseOrganizationPage";
import { codeSchema, loginSchema } from "./schemas";

export default function LoginPage() {
  const { t } = useTranslation();
  const login = useLogin();
  const verify = useVerifyTotp();
  const [step, setStep] = useState<"credentials" | "totp">("credentials");
  const [organizations, setOrganizations] = useState<OrganizationOut[] | null>(null);
  const credentials = useForm({
    initialValues: { email: "", password: "" },
    validate: zodResolver(loginSchema, { errorPriority: "first" }),
  });
  const codeForm = useForm({
    initialValues: { code: "" },
    validate: zodResolver(codeSchema, { errorPriority: "first" }),
  });

  function handleResult(r: LoginResult) {
    if (r.status === "totp_required") setStep("totp");
    else if (r.status === "choose_organization") setOrganizations(r.organizations ?? []);
  }

  if (organizations) return <ChooseOrganizationPage organizations={organizations} />;

  const tr = (msg: unknown) => (typeof msg === "string" ? t(msg) : undefined);

  if (step === "totp") {
    return (
      <Container size="xs" py="xl">
        <form
          onSubmit={codeForm.onSubmit((v) => verify.mutate(v, { onSuccess: handleResult }))}
          noValidate
        >
          <Stack>
            <Title order={2}>{t("auth.totp.title")}</Title>
            <Text c="dimmed">{t("auth.totp.description")}</Text>
            {verify.error && <Alert color="red">{t(errorKey(verify.error))}</Alert>}
            <TextInput
              label={t("auth.totp.code")}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              {...codeForm.getInputProps("code")}
              error={tr(codeForm.errors.code)}
            />
            <Button type="submit" loading={verify.isPending}>
              {t("auth.totp.submit")}
            </Button>
          </Stack>
        </form>
      </Container>
    );
  }

  return (
    <Container size="xs" py="xl">
      <form
        onSubmit={credentials.onSubmit((v) => login.mutate(v, { onSuccess: handleResult }))}
        noValidate
      >
        <Stack>
          <Title order={2}>{t("auth.login.title")}</Title>
          {login.error && <Alert color="red">{t(errorKey(login.error))}</Alert>}
          <TextInput
            label={t("auth.login.email")}
            type="email"
            autoComplete="username"
            {...credentials.getInputProps("email")}
            error={tr(credentials.errors.email)}
          />
          <PasswordInput
            label={t("auth.login.password")}
            autoComplete="current-password"
            {...credentials.getInputProps("password")}
            error={tr(credentials.errors.password)}
          />
          <Button type="submit" loading={login.isPending}>
            {t("auth.login.submit")}
          </Button>
        </Stack>
      </form>
    </Container>
  );
}
