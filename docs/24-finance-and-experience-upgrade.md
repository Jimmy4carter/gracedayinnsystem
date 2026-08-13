# Finance and experience upgrade

## Finance

The system now has a formal ledger foundation:

- `LedgerAccount` provides a chart of accounts for receivables, cash, bank/POS clearing, tax payable, revenue, and refunds.
- `JournalEntry` and `JournalLine` enforce immutable, balanced debit/credit postings.
- Folio charges, payment receipts, and refunds post operational journal entries automatically.
- `PaymentStatusEvent` records payment lifecycle changes append-only.
- `TaxLiability` preparation creates a controlled tax-liability journal.
- `BankAccount`, `BankStatementLine`, and `BankReconciliation` provide a period-based reconciliation workflow with explicit differences.

This is a strong hotel/PMS accounting foundation. It still needs production chart-of-account mapping, external bank-feed import, tax authority filing rules, and accountant approval endpoints before being treated as a statutory general ledger.

## Experience

- Reservation lists now show Paid, Part-paid, or Unpaid state and the current balance directly beside operational actions.
- Payment selection prefills the outstanding balance and requires an electronic reference for non-cash tenders.
- Room editing has a room switcher so staff can move between rooms without returning to a list and losing context.
- Shared public styles now include focus-visible states, reduced-motion support, shimmer loaders, hover feedback, and clearer form focus.
- The reception billboard is available at `/billboard/`; it rotates welcome content, active promotions, room inventory, and hotel announcements, supports pause/fullscreen keyboard controls, shows a clock, and works without JavaScript-only content.

## Operating recommendation

Open `/billboard/` in a dedicated reception browser profile, enable fullscreen, and configure the display not to sleep. Keep media concise and high contrast; avoid sensitive guest information. Use the daily financial audit pack and bank reconciliation views as the accounting close evidence.
