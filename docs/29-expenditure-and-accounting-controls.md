# Expenditure and Accounting Controls

This runbook defines the operating controls for GraceDay Inn's expenditure, journal, tax and reconciliation features. They are strong internal controls for a single-property hotel, but they do not replace professional accounting advice, statutory returns or an external audit.

## Roles and separation of duties

- A manager or administrator creates and submits an expenditure with its business date, category, supplier, description, net amount, tax, payment method, reference and supporting evidence.
- An accountant or administrator reviews and approves or rejects it. Except for a superuser emergency override, the submitter cannot approve the same expenditure.
- An accountant or administrator records payment only after approval. Every transition requires a note and creates an append-only status event.
- Only an administrator can void a posted expenditure. Posted amounts and accounting classifications are immutable; corrections use controlled reversals rather than editing history.
- Evidence is available only through the protected download endpoint and is never intended to be served directly from `/media/private/`.

## Daily finance routine

1. The front desk opens its assigned cashier terminal and shift before receiving cash or point-of-sale payments.
2. Every reservation payment is recorded against the reservation/folio and produces an append-only payment-status event plus balanced journal lines.
3. The cashier closes the shift, counts tender by payment method and records the variance explanation.
4. The manager submits all same-day expenses and attaches readable supplier evidence.
5. The accountant reviews independent evidence, rejects duplicates or incomplete entries, and approves valid items.
6. The accountant records approved payments against the correct cash/bank method and reviews the daily financial audit for missing or unbalanced journals.
7. Exceptions remain open until resolved; never alter database rows to force a report to balance.

## Weekly and month-end routine

1. Reconcile each bank or point-of-sale clearing account to the provider statement for a non-overlapping period.
2. Investigate the difference between the statement closing balance and the ledger closing balance; retain the explanation and reviewer identity.
3. Review approved-but-unpaid obligations, expenditure by category, input VAT, output VAT and the net VAT position.
4. Export the Excel expenditure register and PDF management report into the approved period evidence folder.
5. Confirm journal debits equal credits and run `python manage.py reconcile_system --json`.
6. Have the accountant confirm tax recoverability and the statutory VAT filing amount. Input VAT in the system is explicitly subject to recoverability under applicable law.

## Accounting treatment

A paid expenditure posts the net amount to the configured expense account, eligible tax to account `1150 Input VAT recoverable`, and the gross amount to cash or the bank/POS clearing account. Revenue-side VAT remains output VAT. Reports show output VAT, input VAT paid and the net VAT position separately.

The operating-result view is cash-basis operational reporting. It is useful for daily management but is not an accrual-basis income statement and must not be presented as audited statutory accounts.

## Bank-account privacy

The portal stores a display name and only the last four account digits. Do not enter full bank account numbers, card numbers, passwords or online-banking credentials. Map each configured account to an active asset ledger account before reconciling it.

## Required launch evidence

- One complete front-desk shift with cash and POS examples and a signed variance review.
- One manager-submitted expenditure approved and paid by an independent accountant account.
- One rejected expenditure and one controlled void, confirming status history remains visible.
- A balanced journal export, a bank reconciliation and Excel/PDF reports reviewed by the hotel accountant.
- A professional review of the chart of accounts, VAT handling, retention policy and local statutory obligations before accepting real transactions.
