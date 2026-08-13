# GraceDay Inn — Product Delivery Documentation

This folder is the source of truth for completing GraceDay Inn as a production-grade hotel website, booking engine, property management system (PMS), point-of-sale/front-desk system, and management oversight portal.

## Start here

1. Read [01-current-state-audit.md](01-current-state-audit.md) for what the repository actually contains today.
2. Approve the product boundaries and operating assumptions in [02-product-requirements.md](02-product-requirements.md).
3. Approve the role and permission matrix in [03-roles-and-workflows.md](03-roles-and-workflows.md).
4. Use [04-target-architecture.md](04-target-architecture.md) as the technical direction.
5. Execute phases in [05-implementation-roadmap.md](05-implementation-roadmap.md).
6. Track individual work items in [06-master-backlog.md](06-master-backlog.md).
7. Use the specialist plans for [integrations](07-integrations-and-communications.md), [quality and operations](08-quality-security-and-operations.md), and [design](09-design-system-and-experience.md).
8. Run the commands in [10-verified-baseline.md](10-verified-baseline.md) before starting and handing off implementation work.
9. Review accepted increments and remaining boundaries in [11-implementation-log.md](11-implementation-log.md).
10. Configure and validate deployment using [12-production-configuration.md](12-production-configuration.md).
11. Operate the service with the [front-desk](13-operator-runbook.md), [admin](14-admin-runbook.md), [management](15-management-runbook.md), [incident](16-incident-response-runbook.md), [backup/restore](17-backup-restore-runbook.md), and [deployment/rollback](18-deployment-rollback-runbook.md) runbooks.
12. Activate and verify vendor-neutral tracing, metrics and alert routing with the [observability runbook](22-observability-runbook.md).
12. Certify each physical front-desk combination with the [printer checklist](19-printer-certification-checklist.md).
13. Operate access, correction, anonymization, retention, and legal-hold workflows with the [privacy governance runbook](20-privacy-governance-runbook.md).
14. Enroll staff MFA, revoke JWTs, and perform controlled account recovery with the [MFA and token operations runbook](21-mfa-and-token-operations.md).
15. Use the [current-state review](23-current-state-review.md) for the finance controls, frontend/backend alignment, and explicitly remaining boundaries.
16. Use the [finance and experience upgrade](24-finance-and-experience-upgrade.md) for the ledger, reconciliation, payment-event, continuity, and reception billboard procedures.

## Delivery principles

- One reservation, folio, payment, room-state, and audit model must serve the public website and every portal.
- Permissions are enforced in backend services and APIs; hiding a menu item is not authorization.
- Financial records are append-only or explicitly reversed/refunded, never silently overwritten.
- Every material operation records who did it, when, where, and why.
- Availability and price are revalidated inside a database transaction before confirmation.
- The front desk must remain fast on modest hardware and support 80 mm thermal receipts.
- Management sees trusted, explainable metrics with drill-down to source transactions.
- Email and chat activity are logged without storing unnecessary secrets or sensitive message data.

## Definition of “complete”

Version 1 is complete when a guest can discover and book a room, staff can operate the entire stay from reservation through checkout, management can inspect performance and raise queries, Brevo communications are traceable, receipts print reliably, permissions prevent cross-role access, critical workflows have automated tests, and the service is deployable with monitoring, backups, and recovery procedures.

The existing root-level `implementation_plan.md` and `walkthrough.md` describe an earlier refinement and are historical context. This folder supersedes them for future delivery.
