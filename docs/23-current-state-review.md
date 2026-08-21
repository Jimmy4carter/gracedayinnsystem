# Current-state review: frontend, operations, and finance

## What was corrected

- Financial report headline totals are now scoped to the selected reporting window and are sourced from folio entries, completed payments, and refunds instead of lifetime invoice aggregates.
- Accountant access is aligned across reports, exports, cashier shifts, payment recording, and the new financial-audit workspace.
- Financial audit packs are period-scoped, hash-sealed, exception-aware, immutable after creation, and require an independent manager/admin approval.
- The audit control pack surfaces open cashier shifts, cash variance, completed payments without receipts, and completed payments without a folio link.
- The report UI no longer claims a full double-entry ledger where the current domain model only provides folio debit/credit controls.

## Standard operating model

1. Front desk records every reservation payment against the invoice and folio, with an active cashier shift for cash and a transaction reference for electronic tenders.
2. The cashier closes the shift with counted cash. A variance is retained as an immutable exception and cannot be silently edited away.
3. Accounting prepares a daily pack for the completed business date, checks tender totals, receipts, folio links, open shifts, refunds, and receivables, then records evidence outside the front-desk workflow.
4. A manager or administrator independently approves the pack. The preparer cannot approve their own pack.
5. Management reviews the weekly trend and unresolved exceptions; corrections are compensating entries with a reason and actor trail.

## Remaining deliberate gaps

The system now has a strong control layer, but it is not yet a statutory general ledger. Folio entries are still the operational sub-ledger; a future phase should add a chart of accounts and balanced journal lines for bank reconciliation, tax liabilities, deferred revenue, and expense posting. Payment lifecycle history should also be expanded into an append-only event stream for status changes and external settlement confirmation.

The public booking experience is visually modern and responsive, but the next usability pass should test the complete mobile booking journey, keyboard navigation, payment error recovery, and thermal-print preview with a real device profile. Those are verification tasks rather than assumptions of completeness.
