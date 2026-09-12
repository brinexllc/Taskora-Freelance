# TRUST-01 / SEC-02 / SEC-03 / GOV-01 — account security implementation

The changes are implemented locally. They do not certify production, approve legal documents, verify a payment beneficiary, or rotate any infrastructure secret.

## Browser sessions and operators

Browser login, registration, password reset and password change create a database-backed Django session. The HTTP response contains a user object and a masked CSRF token, never a permanent authentication token. The cookie is `taskora_session`, HttpOnly, SameSite=Lax; Secure is mandatory in staging/production. Its default absolute lifetime is 12 hours, configurable from 5 minutes to 7 days. Cookie authentication validates a matching unrevoked `BrowserSession` record. Session secrets are not returned by the device-list API.

The frontend must use one origin with an `/api/` proxy, send credentials, load `/api/auth/csrf/`, and send `X-CSRFToken` on mutations, including login. Login and MFA elevation rotate credentials. Store the returned CSRF token in memory; it is not an authentication credential. MFA enable and sensitive confirmation also return a rotated `csrf_token`.

Logout revokes the current server session. Password change/reset revoke all tracked sessions and legacy tokens, then create one new session. Sessions established by ordinary Django admin password login cannot access admin pages until authentication through the MFA-protected Taskora flow. Staff/superusers without MFA get a restricted enrollment session. An existing MFA user's password recovery also yields a restricted session until the factor is supplied. Administrative mutations require an enrolled factor, a tracked session with MFA, and a password plus new TOTP confirmation within 5 minutes.

TOTP uses PyOTP, six digits and a 30-second step with a one-step clock tolerance. Consumed counters are locked and saved in the shared database to reject replay. Pending enrollment expires in 10 minutes. Secrets are Fernet-encrypted; `SECURITY_MFA_ENCRYPTION_KEY` must be a separate Fernet key in staging/production. Protect and back up this key separately from the database. The deterministic key derived from the local Django secret is only a local/test fallback. Clock synchronization and MFA enrollment of every privileged account must be checked before enabling real money. Re-enrollment after losing a factor requires an individually audited operator/infrastructure recovery procedure; password recovery cannot silently remove MFA.

## Legacy transition

Permanent DRF tokens are no longer issued. Legacy Token authentication is disabled by default. If the owner approves a brief transition, `SECURITY_LEGACY_TOKEN_UNTIL` must specify an absolute timezone-aware deadline. `SECURITY_LEGACY_TOKEN_MAX_AGE_SECONDS` additionally limits token age (default 24 hours). This bridge permits only reads by ordinary users; mutations and operator use require browser sessions. After the agreed window, unset the deadline and run `manage.py revoke_legacy_tokens --apply`. The command without `--apply` reports only the count. Revoking a token does not reveal its value.

“New tokens” above means the old permanent DRF Token scheme. Optional non-browser clients have a separate `ScopedApiToken` mechanism. `POST /api/auth/api-tokens/` requires a valid cookie session, CSRF and the current password, and accepts `name`, `password`, `scopes` and `expires_in` (300–86400 seconds, default 3600). The only scopes are `profile:read`, `projects:read`, `contracts:read`. The one-time response contains `token`; clients use `Authorization: Bearer taskora_api_…` against the backend API directly (the browser proxy deliberately strips Authorization). Only SHA-256 of the high-entropy secret is stored. `GET /api/auth/api-tokens/` lists metadata without secrets; `DELETE /api/auth/api-tokens/<id>/` revokes an individual token. Password change/reset and MFA enable/disable revoke every such token. Staff/superusers cannot issue or use them. They never authorize mutations, wallets, payments or admin access, and ordinary participant checks still protect private records. The web app must not use or persist these integration credentials for its browser login.

## Contact evidence

Email and telephone verification are separate from passport declarations, identity-provider verification and skill validation. Codes are hashed, expire after 10 minutes, allow at most five failed attempts and can be consumed only once by the authenticated account for the unchanged destination. A resend invalidates the previous challenge. Model/admin and API contact edits reset verification. The financial guard also compares the confirmed contact snapshot with the current value, so a direct queryset contact edit cannot retain financial authorization.

`require_verified_contact(user, channel=None)` enforces `FINANCIAL_CONTACT_CHANNEL` (default `phone`; `email` is an explicit policy option). An unverified account can still edit its profile. Errors return a machine-readable `contact_verification_required` reason. Existing profiles receive empty evidence during migration; no historical contact confirmation is fabricated. Beneficiary confirmation remains a distinct payment-operations check.

## Shared limits

`SecurityRateBucket` stores HMAC identifiers and fixed-window counters in the shared application database. A conditional SQL increment enforces the maximum atomically across workers. It does not depend on Django's per-process memory cache. Independent IP and account counters apply to login, reset, verification, contact delivery and sensitive mutations. Aliases normalize to a shared account key when an account exists. Provider callbacks retain their explicit exemption from user mutation throttles.

Only configured `SECURITY_TRUSTED_PROXY_CIDRS` may supply a forwarded IP; the parser walks the forwarded chain from the trusted edge and ignores user-prepended values. With an empty configuration only the connecting IP is used. Confirm the actual ingress/proxy CIDRs during deployment; guessing these networks can either collapse users into one limit or permit spoofing. A database/limiter failure returns 503 before sending SMS. Recovery repeats use identical account-independent response/status rules, including exhausted limits and delivery failure; the old account-only 60-second 429 branch is removed.

The default same-origin frontend proxy does not forward untrusted client IP headers. Until the deployed ingress has a verified, sanitized client-IP channel, browser requests therefore share the frontend's connecting-IP budget. This prevents spoof-based bypass but can throttle legitimate users together. Validate and configure that channel with the actual ingress topology before a multi-user production pilot; never fix it by trusting an arbitrary incoming X-Forwarded-For string.

Run `manage.py purge_security_state` periodically to clear expired throttle buckets and Django sessions. Verification and consent evidence is retained pending an approved retention policy. SMTP/SMS delivery and timing over real networks need a separate production validation; local mail tests do not prove external delivery.

## Published terms and consent

`GET /api/legal/current/?lang=ru|uz|uz-cyrl|en` returns the version, SHA-256 of the canonical content, language and actual content. The default `legal_content.json` is a snapshot of existing translated legal-page copy generated by `scripts/snapshot_legal_content.cjs`, explicitly `approved: false`. It contains no invented operator details or support channels. Operator and support details are included in the hashed snapshot when populated.

Registration supplies `terms_version` and `terms_hash` for the displayed language. A stale revision rolls the registration transaction back. `LegalConsent` keeps version, hash, language, acceptance time and the full content snapshot. Existing users can explicitly accept a current revision using `/api/auth/consent/`. Their old timestamp is not turned into invented historical evidence.

Publish reviewed content through `LEGAL_CONTENT_PATH`, update its version, fill genuine operator/support fields and obtain the owner's approval. Legal review of minors, personal data, disputes, refunds, payout timing and the financial arrangement remains external and **not performed**. Internal confirmation is not E-IMZO/ONEID signing; internal reserves are not represented as legally certified banking escrow.

## Verification and remaining deployment evidence

The automated tests in `marketplace.test_security` cover CSRF including unauthenticated login, cookie flags, logout/copy replay, individual and other-session revocation, expiry, password revocation, finite legacy transition, contact expiry/attempts/replay/ownership/change, recovery response parity, fail-closed SMS limiting, legal revision binding, MFA enrollment/replay/login, operator confirmation expiry and admin bypass rejection. `SharedLimiterProcessTests` runs two independent Python processes against the isolated PostgreSQL test database and checks that together they consume exactly one 17-request budget. It intentionally skips SQLite; a SQLite pass cannot establish this property.

Production origins/cookies, deployed SHA/migrations, trusted proxy configuration, actual operator permissions, independent factor enrollment, SMTP/SMS, old-token revocation and the release approval remain checks for the owner in the production release passport. No external success is claimed by this implementation.

Implementation references: [Django server sessions](https://docs.djangoproject.com/en/6.0/topics/http/sessions/) and [Django CSRF](https://docs.djangoproject.com/en/6.0/howto/csrf/).
