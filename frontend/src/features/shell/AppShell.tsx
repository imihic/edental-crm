import { Anchor, Container, Group, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router-dom";
import { type Me } from "../../api/auth";
import SessionControls from "./SessionControls";

type NavItem = { to: string; label: string; managerOnly?: boolean };

const NAV: NavItem[] = [
  { to: "/patients", label: "nav.patients" },
  { to: "/leads", label: "nav.leads" },
  { to: "/imports", label: "nav.imports", managerOnly: true },
  { to: "/settings/enquiry-form", label: "nav.enquiryForm", managerOnly: true },
  { to: "/staff", label: "nav.staff", managerOnly: true },
];

export default function AppShell({ me }: { me: Me }) {
  const { t } = useTranslation();
  const roles = me.staff.roles.map((r) => t(`roles.${r}`, { defaultValue: r })).join(", ");
  const isManager = me.staff.roles.includes("clinic_manager");
  const items = NAV.filter((n) => !n.managerOnly || isManager);

  return (
    <>
      <Group component="header" justify="space-between" p="md" wrap="wrap">
        <Group>
          <Text fw={700}>{me.organization.name}</Text>
          <Text>
            {me.staff.full_name} ({roles})
          </Text>
        </Group>
        <SessionControls me={me} />
      </Group>
      <Group component="nav" aria-label={t("nav.label")} px="md" gap="lg" wrap="wrap">
        {items.map((n) => (
          <Anchor key={n.to} component={NavLink} to={n.to}>
            {t(n.label)}
          </Anchor>
        ))}
      </Group>
      <Container component="main" py="md">
        <Outlet />
      </Container>
    </>
  );
}
