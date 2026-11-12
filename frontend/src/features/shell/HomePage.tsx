import { List, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { type Me } from "../../api/auth";

export default function HomePage({ me }: { me: Me }) {
  const { t } = useTranslation();
  return (
    <>
      <Title order={2}>{t("shell.home.title")}</Title>
      <Title order={4} mt="md">
        {t("shell.home.clinics")}
      </Title>
      {me.clinics.length === 0 ? (
        <Text c="dimmed">{t("shell.home.noClinics")}</Text>
      ) : (
        <List>
          {me.clinics.map((c) => (
            <List.Item key={c.id}>{c.name}</List.Item>
          ))}
        </List>
      )}
    </>
  );
}
