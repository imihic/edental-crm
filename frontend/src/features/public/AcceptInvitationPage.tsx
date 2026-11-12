import { Alert, Anchor, Button, Container, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { errorKey } from "../../api/auth";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { codeSchema } from "../auth/schemas";

type Schemas = components["schemas"];
type Invitation = Schemas["PublicInvitationOut"];
type AcceptBody = Pick<Schemas["AcceptInvitationIn"], "password"> & Partial<Schemas["AcceptInvitationIn"]>;
type InvitationState = { invitation: Invitation } | { error: unknown } | { accepted: true };

function invitationErrorKey(error: unknown) {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "not_found":
      case "invitation_expired":
      case "invitation_used":
      case "invitation_revoked":
        return `invitation.errors.${error.code}`;
      case "already_staff":
        return "staff.errors.already_staff";
    }
  }
  return errorKey(error);
}

function isUnavailable(error: unknown) {
  return error instanceof ApiError && (error.status === 404 || error.status === 410);
}

function AcceptForm({
  invitation,
  acceptPath,
  onAccepted,
  onUnavailable,
}: {
  invitation: Invitation;
  acceptPath: string;
  onAccepted: () => void;
  onUnavailable: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const [existing, setExisting] = useState(invitation.account_exists);
  const [codeRequired, setCodeRequired] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const form = useForm({
    initialValues: { password: "", confirmation: "", code: "" },
    validate: {
      password: (password) => {
        if (existing) return password ? null : "auth.validation.passwordRequired";
        return [...password].length < 12 ? "invitation.passwordLength" : null;
      },
      confirmation: (confirmation, { password }) =>
        !existing && confirmation !== password ? "invitation.passwordMismatch" : null,
      code: (code) => codeRequired ? codeSchema.shape.code.safeParse(code).error?.issues[0]?.message : null,
    },
  });

  async function submit({ password, code }: typeof form.values) {
    if (pending) return;
    setPending(true);
    setError(undefined);
    const body: AcceptBody = codeRequired ? { password, code: code.trim() } : { password };
    try {
      await apiFetch<Schemas["AcceptedOut"]>(acceptPath, { method: "POST", body });
      onAccepted();
    } catch (err) {
      const accountAppeared = err instanceof ApiError && (
        (err.status === 409 && err.code === "account_exists_retry") ||
        (!existing && err.status === 401 && err.code === "invalid_credentials")
      );
      if (isUnavailable(err)) {
        onUnavailable(err);
      } else if (err instanceof ApiError && err.status === 401 && err.code === "invalid_code") {
        setExisting(true);
        setCodeRequired(true);
        setError(codeRequired ? "auth.errors.invalid_code" : "invitation.errors.codeRequired");
      } else if (accountAppeared) {
        setExisting(true);
        setCodeRequired(false);
        form.reset();
        setError("invitation.errors.account_exists_retry");
      } else {
        setError(invitationErrorKey(err));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={form.onSubmit(submit)} noValidate>
      <Stack>
        <Text>{t("invitation.organization", { organization: invitation.organization_name })}</Text>
        <Text>{invitation.full_name}<br />{invitation.email}</Text>
        {existing && <Text>{t("invitation.existingAccount")}</Text>}
        {error && <Alert color="red" role="alert">{t(error)}</Alert>}
        <PasswordInput
          label={t(existing ? "auth.login.password" : "invitation.newPassword")}
          autoComplete={existing ? "current-password" : "new-password"}
          disabled={pending}
          {...form.getInputProps("password")}
          error={form.errors.password && t(String(form.errors.password))}
        />
        {!existing && (
          <PasswordInput
            label={t("invitation.confirmPassword")}
            autoComplete="new-password"
            disabled={pending}
            {...form.getInputProps("confirmation")}
            error={form.errors.confirmation && t(String(form.errors.confirmation))}
          />
        )}
        {codeRequired && (
          <TextInput
            label={t("auth.totp.code")}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            disabled={pending}
            {...form.getInputProps("code")}
            error={form.errors.code && t(String(form.errors.code))}
          />
        )}
        <Button type="submit" loading={pending}>{t("invitation.title")}</Button>
      </Stack>
    </form>
  );
}

function InvitationView({ token }: { token: string }) {
  const { t } = useTranslation();
  const [state, setState] = useState<InvitationState | null>(null);
  const [attempt, setAttempt] = useState(0);
  const path = `/api/public/invitations/${encodeURIComponent(token)}`;

  useEffect(() => {
    let current = true;
    void apiFetch<Invitation>(path).then(
      (invitation) => { if (current) setState({ invitation }); },
      (error: unknown) => { if (current) setState({ error }); },
    );
    return () => { current = false; };
  }, [path, attempt]);

  if (!state) return <Text role="status">{t("common.loading")}</Text>;
  if ("error" in state) {
    return (
      <>
        <Alert color="red" role="alert">{t(invitationErrorKey(state.error))}</Alert>
        {!isUnavailable(state.error) && (
          <Button onClick={() => { setState(null); setAttempt((value) => value + 1); }}>{t("common.retry")}</Button>
        )}
      </>
    );
  }
  if ("accepted" in state) {
    return (
      <>
        <Text role="status">{t("invitation.accepted")}</Text>
        <Anchor component={Link} to="/login" replace rel="noreferrer">{t("auth.login.submit")}</Anchor>
      </>
    );
  }
  return (
    <AcceptForm
      invitation={state.invitation}
      acceptPath={`${path}/accept`}
      onAccepted={() => setState({ accepted: true })}
      onUnavailable={(error) => setState({ error })}
    />
  );
}

export default function AcceptInvitationPage() {
  const { token } = useParams<"token">();
  const { t } = useTranslation();

  return (
    <Container component="main" size="xs" py="xl">
      <Stack>
        <Title order={1}>{t("invitation.title")}</Title>
        {token ? (
          <InvitationView key={token} token={token} />
        ) : (
          <Alert color="red" role="alert">{t("invitation.errors.not_found")}</Alert>
        )}
      </Stack>
    </Container>
  );
}
