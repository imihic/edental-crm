import { Alert, Button, Group, NativeSelect } from "@mantine/core";
import { useIsMutating } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { errorKey, useChooseOrganization, useLogout, useOrganizations, type Me } from "../../api/auth";

export default function SessionControls({ me }: { me: Me }) {
  const { t } = useTranslation();
  const logout = useLogout();
  const showSwitcher = me.organizations_count > 1;
  const orgs = useOrganizations(showSwitcher);
  const choose = useChooseOrganization();
  const mutationPending = useIsMutating() > 0;

  const options = (orgs.data?.organizations ?? [me.organization]).map((o) => ({
    value: o.id,
    label: o.name,
  }));

  return (
    <Group>
      {showSwitcher && (
        <NativeSelect
          aria-label={t("shell.switchOrganization")}
          value={me.organization.id}
          data={options}
          disabled={mutationPending}
          onChange={(e) => {
            const id = e.currentTarget.value;
            if (id !== me.organization.id) {
              choose.mutate({ organization_id: id });
            }
          }}
        />
      )}
      <Button variant="default" loading={logout.isPending} disabled={choose.isPending} onClick={() => logout.mutate()}>
        {t("shell.logout")}
      </Button>
      {choose.error && <Alert color="red">{t(errorKey(choose.error))}</Alert>}
      {logout.error && <Alert color="red">{t(errorKey(logout.error))}</Alert>}
    </Group>
  );
}
