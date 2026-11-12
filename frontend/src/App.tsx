import { Alert, Button, Center, Loader, Stack } from "@mantine/core";
import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, Route, Routes, useParams } from "react-router-dom";
import { errorKey, useMe, useTenantSessionFence } from "./api/auth";
import ChooseOrganizationPage from "./features/auth/ChooseOrganizationPage";
import LoginPage from "./features/auth/LoginPage";
import TotpEnrollPage from "./features/auth/TotpEnrollPage";

const AppShell = lazy(() => import("./features/shell/AppShell"));
const HomePage = lazy(() => import("./features/shell/HomePage"));
const PatientsPage = lazy(() => import("./features/people/PatientsPage"));
const PatientDetailPage = lazy(() => import("./features/people/PatientDetailPage"));
const LeadsPage = lazy(() => import("./features/people/LeadsPage"));
const LeadDetailPage = lazy(() => import("./features/people/LeadDetailPage"));
const ImportPage = lazy(() => import("./features/people/ImportPage"));
const EnquiryFormSettingsPage = lazy(() => import("./features/people/EnquiryFormSettingsPage"));
const StaffPage = lazy(() => import("./features/staff/StaffPage"));
const PublicEnquiryPage = lazy(() => import("./features/public/PublicEnquiryPage"));
const AcceptInvitationPage = lazy(() => import("./features/public/AcceptInvitationPage"));

const Spinner = () => (
  <Center h="100vh">
    <Loader />
  </Center>
);

function PatientRoute() {
  const { id } = useParams();
  return <PatientDetailPage key={id} />;
}

function LeadRoute() {
  const { id } = useParams();
  return <LeadDetailPage key={id} />;
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/enquiry/:key" element={<PublicEnquiryPage />} />
        <Route path="/invite/:token" element={<AcceptInvitationPage />} />
        <Route path="/*" element={<StaffApp />} />
      </Routes>
    </Suspense>
  );
}

function StaffApp() {
  const { t } = useTranslation();
  const { data: me, isPending, error, refetch } = useMe();
  const tenantTransition = useTenantSessionFence(me);
  if (isPending || tenantTransition) return <Spinner />;
  if (error) {
    return (
      <Center h="100vh">
        <Stack align="center">
          <Alert color="red">{t(errorKey(error))}</Alert>
          <Button onClick={() => void refetch()}>{t("common.retry")}</Button>
        </Stack>
      </Center>
    );
  }

  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={me ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route
          path="/choose-organization"
          element={me ? <Navigate to="/" replace /> : <ChooseOrganizationPage />}
        />
        <Route
          path="/totp-enroll"
          element={
            !me ? (
              <Navigate to="/login" replace />
            ) : me.totp_enrollment_required ? (
              <TotpEnrollPage me={me} />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/"
          element={
            !me ? (
              <Navigate to="/login" replace />
            ) : me.totp_enrollment_required ? (
              <Navigate to="/totp-enroll" replace />
            ) : (
              <AppShell key={me.staff.id} me={me} />
            )
          }
        >
          <Route index element={me ? <HomePage me={me} /> : null} />
          <Route path="patients" element={<PatientsPage />} />
          <Route path="patients/:id" element={<PatientRoute />} />
          <Route path="leads" element={<LeadsPage />} />
          <Route path="leads/:id" element={<LeadRoute />} />
          <Route
            element={
              me?.staff.roles.includes("clinic_manager") ? <Outlet /> : <Navigate to="/" replace />
            }
          >
            <Route path="imports" element={<ImportPage />} />
            <Route path="settings/enquiry-form" element={<EnquiryFormSettingsPage />} />
            <Route path="staff" element={<StaffPage clinics={me?.organization_clinics ?? []} />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
