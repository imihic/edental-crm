# Accounts are separate from Staff Members

A person signs in with one **Account** (email, password, TOTP). Their work for each Organization is a separate **Staff Member** row, which carries the roles and Clinics for that Organization. Dentists commonly work for two unrelated private clinics; with one email tied to one Organization, they would need two emails. A globally unique email column inside a tenant table would also tell one clinic that an address exists at another.

After the password (and TOTP) step, an Account with several active Staff Members picks an Organization. The session is then bound to exactly one Staff Member and one Organization, so Row-Level Security (ADR 0001) is unchanged.

## Considered options

- **One email = one Organization**: simpler, but forces duplicate identities for multi-clinic dentists. Changing it later would touch every session, audit entry and foreign key.

## Consequences

- `accounts` has no `organization_id`. Its RLS policy lets the app see only the signed-in Account, or Accounts that have a Staff Member in the current Organization.
- Sign-in reads Accounts and memberships before any Organization is known. It does so only through two narrow `SECURITY DEFINER` functions.
- The second factor belongs to the Account. It is mandatory while the active Staff Member holds the Clinic Manager role.
