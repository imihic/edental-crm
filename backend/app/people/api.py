from flask_openapi3 import APIBlueprint

from app.people.consents.route import api as consents_api
from app.people.contact_promote.route import api as contact_promote_api
from app.people.enquiry_form.route import api as enquiry_form_api
from app.people.guardians.route import api as guardians_api
from app.people.import_commit.route import api as import_commit_api
from app.people.import_preview.route import api as import_preview_api
from app.people.imports_list.route import api as imports_list_api
from app.people.lead_convert.route import api as lead_convert_api
from app.people.lead_create.route import api as lead_create_api
from app.people.lead_detail.route import api as lead_detail_api
from app.people.lead_stage.route import api as lead_stage_api
from app.people.leads_list.route import api as leads_list_api
from app.people.merge.route import api as merge_api
from app.people.patient_create.route import api as patient_create_api
from app.people.patient_detail.route import api as patient_detail_api
from app.people.patient_enquiry_create.route import api as patient_enquiry_create_api
from app.people.patient_reveal_oib.route import api as patient_reveal_oib_api
from app.people.patient_update.route import api as patient_update_api
from app.people.patients_list.route import api as patients_list_api
from app.people.public_enquiry.route import api as public_enquiry_api
from app.platform.openapi_merge import register_slices

people_api = APIBlueprint("people", __name__)
register_slices(
    people_api,
    (
        patients_list_api,
        patient_create_api,
        patient_detail_api,
        patient_update_api,
        patient_reveal_oib_api,
        guardians_api,
        contact_promote_api,
        leads_list_api,
        lead_create_api,
        lead_detail_api,
        lead_stage_api,
        lead_convert_api,
        patient_enquiry_create_api,
        consents_api,
        merge_api,
        import_preview_api,
        import_commit_api,
        imports_list_api,
        enquiry_form_api,
        public_enquiry_api,
    ),
)
