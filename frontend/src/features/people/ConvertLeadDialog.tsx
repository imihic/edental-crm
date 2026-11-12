import { Modal } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { peopleActionErrorKey, useConvertLead, type LeadDetail } from "./leadApi";
import PatientForm from "./PatientForm";

export default function ConvertLeadDialog({ lead, onClose }: { lead: LeadDetail; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const convert = useConvertLead(lead.id);
  const name = lead.full_name.trim();
  const lastSpace = name.lastIndexOf(" ");

  return (
    <Modal opened title={t("people.conversion.title")} onClose={onClose} size="lg">
      <PatientForm
        defaults={{
          first_name: lastSpace === -1 ? name : name.slice(0, lastSpace).trimEnd(),
          last_name: lastSpace === -1 ? "" : name.slice(lastSpace + 1),
          phone: lead.phone ?? "",
          email: lead.email ?? "",
          preferred_clinic_id: lead.clinic_id,
        }}
        createPatient={convert.mutateAsync}
        duplicateActionLabel={t("people.conversion.confirmDuplicate")}
        errorKey={peopleActionErrorKey}
        onCancel={onClose}
        onSaved={(patient) => navigate(`/patients/${patient.id}`)}
      />
    </Modal>
  );
}
