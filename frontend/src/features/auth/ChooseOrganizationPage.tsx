import { Alert, Button, Container, Loader, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import {
  errorKey,
  useChooseOrganization,
  useOrganizations,
  type OrganizationOut,
} from "../../api/auth";

export default function ChooseOrganizationPage({
  organizations,
}: {
  organizations?: OrganizationOut[];
}) {
  const { t } = useTranslation();
  const query = useOrganizations(organizations === undefined);
  const choose = useChooseOrganization();
  const list = organizations ?? query.data?.organizations;

  return (
    <Container size="xs" py="xl">
      <Stack>
        <Title order={2}>{t("auth.chooseOrganization.title")}</Title>
        <Text c="dimmed">{t("auth.chooseOrganization.description")}</Text>
        {choose.error && <Alert color="red">{t(errorKey(choose.error))}</Alert>}
        {query.error && <Alert color="red">{t(errorKey(query.error))}</Alert>}
        {!list && !query.error && <Loader />}
        {list?.map((org) => (
          <Button
            key={org.id}
            variant="default"
            disabled={choose.isPending}
            loading={choose.isPending && choose.variables?.organization_id === org.id}
            onClick={() => choose.mutate({ organization_id: org.id })}
          >
            {org.name}
          </Button>
        ))}
      </Stack>
    </Container>
  );
}
