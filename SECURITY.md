# Security

This document describes Retrieva's security model, the controls that implement it, and how to
report a vulnerability.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's
[security advisories](https://github.com/RutujaSawant89/Retrieva-/security/advisories/new) rather
than opening a public issue. Include steps to reproduce and the affected version or commit.

## Threat model (summary)

| Threat | Controls |
| --- | --- |
| Cross-tenant data access | Organization filter on every query **and** PostgreSQL Row-Level Security (`FORCE`) enforced through a non-superuser, non-`BYPASSRLS` runtime role; 404 (not 403) for other tenants' resources; tests that query the database directly as the app role |
| Unauthorized access within a tenant | RBAC (admin / analyst / researcher / viewer) checked per endpoint; private documents and collections visible only to owner and admins; conversations and research reports private to their author; membership re-read per request |
| Credential attacks | Argon2id hashing with transparent re-hashing, password policy, constant-time handling of unknown accounts, per-IP auth rate limits, per-user API rate limits (Redis-backed) |
| Token theft | Access tokens in memory only (never `localStorage`); refresh tokens `httpOnly`, `SameSite=Strict`, path-scoped, stored hashed, rotated on use, with family revocation on replay |
| Prompt injection via documents | Sources wrapped in envelopes that document text cannot close; instruction-like content detected and surfaced; system prompt treats sources as data; no tools or actions are exposed to the model; independent verification of every citation |
| Hallucinated or fabricated evidence | Cite-or-abstain prompting, pre-generation abstention gate on reranker scores, post-generation verifier (fabricated labels, unsupported claims, figures not present in sources, wrong page references) |
| Malicious uploads | Extension allow-list, magic-byte / structure validation, size limit enforced while streaming, DOCX zip-bomb guard, files stored outside the web root under generated names, downloads served with `Content-Security-Policy: sandbox` and `nosniff` |
| Sensitive information exposure | Generic 500 responses (details only in logs), correlation IDs instead of stack traces, secrets only from the environment, `.env` files git-ignored |
| Browser attacks | Strict CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`; generated Markdown rendered without raw HTML |
| Repudiation | Audit log of authentication events, membership and role changes, uploads, downloads, deletions, exports and evaluation runs, with IP, user agent and correlation ID |

## Data deletion

* Deleting a document hard-deletes its chunks and embeddings (so it can never be retrieved
  again) and removes the stored file; the document row is soft-deleted to keep the audit trail
  intelligible.
* Deleting a conversation deletes its messages and citations.
* Deleting an evaluation dataset deletes its runs and results.
* Removing a member revokes their refresh tokens for that organization immediately.

## Operational requirements

* Set `ENVIRONMENT=production`; the API refuses to start with a weak `JWT_SECRET` or with
  `COOKIE_SECURE=false` in production.
* Serve over HTTPS (terminate TLS in front of the `web` service).
* Keep `retrieva_app` a non-superuser without `BYPASSRLS`; the API logs a warning at startup if
  its database role could bypass RLS.
* Run Redis so rate limits are shared across API replicas.
* Restrict `/metrics` to the monitoring network.

## Known limitations

* No email delivery: invitation links are shown once to the admin who creates them.
* No SSO/SAML or MFA for Retrieva accounts yet.
* The verifier is heuristic (or NLI-based when configured). It reliably catches fabricated
  citations, missing figures and unsupported sentences with little lexical or semantic overlap,
  but it is not a proof of entailment.
