# Roles, Permissions and Workflows

## Authorization model

Replace ad-hoc role checks with RBAC plus object scope and selected approval rules.

- Capability: a named operation such as `reservation.check_in` or `payment.refund`.
- Scope: own, assigned, department, property or all configured properties.
- Constraints: amount threshold, shift-open requirement, current state, manager approval or reason required.
- Audit: actor, effective role, object, before/after, reason, request ID, IP/device and timestamp.

All web views, APIs, background jobs, exports and Django admin actions must call the same policy layer. Default is deny.

## Baseline roles

| Capability area | Admin | General Manager | Duty Manager | Receptionist/Cashier | Housekeeping | Maintenance | Services | Reservations/Sales | Guest |
|---|---|---|---|---|---|---|---|---|---|
| Property configuration | Manage | View/approve selected | View | No | No | No | No | No | No |
| Users/roles | Manage with audit | View/request | View department | No | No | No | No | No | No |
| Reservations | Full | Full/read | Full operational | Create/update/check-in/out | Assigned room context | Room context | In-house context | Create/update/quote | Own only |
| Rates/discounts | Configure | Approve | Within limit | Quote/limited discount | No | No | No | Quote/limited | View booked price |
| Folios/charges | Full audited | View/approve | Approve within limit | Post/settle during shift | No | Post authorized items | Post authorized items | View deposit | Own documents |
| Refunds/voids | Configure/approve | Approve | Limited approval | Request/execute approved | No | No | No | No | Request |
| Cashier shifts | Inspect/configure | Inspect | Open/close/approve variance | Own shift | No | No | Outlet shift if enabled | No | No |
| Housekeeping | Configure/inspect | Dashboard | Assign/verify | View room readiness | Assigned tasks/update | Related tickets | No | View readiness | Request service |
| Maintenance | Configure/inspect | Dashboard | Assign/approve downtime | Raise/view | Raise/view | Assigned/manage | Raise/view | Raise/view | Report issue |
| Reports | All | Executive/all | Operational | Shift/front desk | Department | Department | Department | Sales | Own stays |
| Management queries | All | Raise/assign/resolve | Respond/raise | Respond assigned | Respond assigned | Respond assigned | Respond assigned | Respond assigned | No |
| Communications | Configure/all | Inspect | Department | Guest threads | Assigned task thread | Ticket thread | Order thread | Leads/campaigns | Own threads |
| Audit/export | Full controlled | Read/export | Read department | Own/shift | Own | Own | Own | Own | Own data request |

The final matrix must be stored as seeded permissions, reviewed with hotel leadership, and covered by automated allow/deny tests. “Admin” does not permit editing immutable financial/audit history.

## Reservation and stay workflow

1. Search sellable inventory using stay dates, occupants, property, rate restrictions and operational blocks.
2. Quote produces an expiring price/policy snapshot.
3. Hold optionally reserves inventory for a short configured time.
4. Booking transaction locks inventory, revalidates price/availability, records guest consent, creates reservation/folio and requests deposit/payment.
5. Status flow: `draft/hold -> pending_payment -> confirmed -> checked_in -> checked_out`; alternate terminal states are `cancelled` and `no_show`.
6. Amendments create history and recalculate only authorized future charges. Room moves retain assignment history.
7. Check-in requires assigned ready room, identity requirements, registration acceptance and configured deposit/authorization.
8. Checkout requires charge review, settlement or approved receivable, key return notes, room-state transition and housekeeping task.

No status can be changed by arbitrary field update; use commands with transition guards.

## Front-desk cashier workflow

1. Staff signs in and opens a cashier shift on a registered terminal with opening float.
2. Every cash receipt, paid-in/out, refund and void is linked to that shift.
3. A completed payment creates immutable tender/ledger entries and an issued receipt.
4. Receipt prints automatically if enabled; print failure does not roll back payment and is visibly retryable.
5. Reprint includes “REPRINT”, count, actor and timestamp.
6. At close, the staff enters counted cash; system calculates variance; threshold breaches require manager approval and note.
7. Shift locks after close. Corrections use new reversal entries, never edits to historical cash movements.

## Management query workflow

1. Manager raises a query from a dashboard metric, report row, reservation, folio, payment, shift or operational task.
2. System snapshots the referenced context and assigns owner/department, priority and due date.
3. Owner acknowledges, comments, adds evidence and proposes resolution.
4. Manager resolves, rejects or reopens. Overdue items escalate.
5. The complete discussion and status history remains auditable; sensitive attachments have scoped access.

## Inquiry and live-chat workflow

- A website inquiry creates a case, acknowledges the sender and routes by topic/availability.
- Chat creates a conversation with anonymous/verified identity state, consent and assigned queue.
- Agents can use approved snippets, see relevant guest/reservation context, convert a thread to inquiry/reservation task, and transfer/escalate.
- Outside hours, collect a message and promise a realistic response window.
- Close captures disposition and optional satisfaction rating. Retention and transcript access follow policy.

## Separation-of-duties rules

- Staff cannot approve their own high-value discount, refund, write-off or cashier variance.
- Users cannot assign themselves privileged roles.
- Financial/audit deletion is prohibited; void/reversal requires reason and privilege.
- Rate and tax changes are effective-dated and do not silently rewrite existing reservation snapshots.
- Management report exports containing personal data require purpose, permission and audit.
