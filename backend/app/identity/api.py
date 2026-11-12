from flask_openapi3 import APIBlueprint

from app.identity.confirm_totp.route import api as confirm_totp_api
from app.identity.csrf.route import api as csrf_api
from app.identity.enroll_totp.route import api as enroll_totp_api
from app.identity.invitations.route import api as invitations_api
from app.identity.login.route import api as login_api
from app.identity.logout.route import api as logout_api
from app.identity.me.route import api as me_api
from app.identity.organizations.route import api as organizations_api
from app.identity.public_invitation.route import api as public_invitation_api
from app.identity.staff_list.route import api as staff_list_api
from app.identity.staff_update.route import api as staff_update_api
from app.identity.verify_totp.route import api as verify_totp_api
from app.platform.openapi_merge import register_slices

auth_api = APIBlueprint("auth", __name__)
register_slices(
    auth_api,
    (
        csrf_api,
        login_api,
        verify_totp_api,
        enroll_totp_api,
        confirm_totp_api,
        organizations_api,
        me_api,
        logout_api,
        staff_list_api,
        staff_update_api,
        invitations_api,
        public_invitation_api,
    ),
)
