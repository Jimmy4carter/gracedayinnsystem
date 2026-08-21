# Front Desk and Cashier Operator Runbook

## Shift start

1. Sign in with your own receptionist account; never share credentials.
2. Confirm the terminal name and 80/58 mm paper profile.
3. Count the opening float, open the cashier shift and verify the X report.
4. Review arrivals, departures, room readiness, inquiries and maintenance blocks.

## Booking and stay

- Search dates before selecting a room. Housekeeping state does not replace a date-bound sales block.
- Capture minimum identity data; store only the last four identity characters.
- Read the itemized rate, supplements, extras, taxes, deposit and cancellation policy before confirmation.
- Public visitors contact the hotel through WhatsApp or the inquiry form. Handle the message in the approved hotel WhatsApp Business account, and record booking/payment actions in the management system rather than treating a chat message as transaction evidence.
- Use explicit check-in, move, extend, no-show and checkout commands. Never edit history directly.
- On the today board, press `/` to focus reservation search, `Alt+N` to open the new-reservation form, and `Alt+T` to open the tape chart. Search accepts reservation number, guest name/username, phone or room number.

## Money and receipts

- Cash requires an open shift. Retry interrupted posting with the same idempotency key.
- Never delete payments or folio entries. Managers post audited adjustments or credit notes.
- Confirm receipt number, amount and terminal before printing. Reprints are numbered and audited.
- At close, enter actual counted cash and explain variance; material variance needs a different manager.

## Contingencies and handover

- Printer unavailable: issue the numbered A4/browser receipt, log failure and reprint later.
- Network unavailable: stop electronic posting and use the controlled continuity log; reconcile before reopening.
- Stop and escalate booking conflicts, wrong room state or suspected duplicates with source references.
- Hand over unresolved exceptions, pending reprints, Z report and variance evidence.
## Incident and lost-and-found operations

- Record an incident immediately with the observed facts, occurrence time, location, severity and related room/reservation. Do not add speculation or unnecessary health/payment identity data.
- Reception may begin investigation; only management resolves or closes an incident. Resolution and closure evidence are mandatory and retained in immutable history.
- Register every found item before moving it. Record the exact secure storage location to establish custody.
- Before recording a claim, capture claimant contact details and the non-secret evidence used to match the item. Never store passwords, PINs, card numbers or copies of unnecessary identity documents.
- Record signed or otherwise approved handover evidence when returning an item. Disposal requires management authorization and documented disposition.
- Housekeeping can register and store items but cannot see claimant contact details or authorize claims/disposal.

## Linen, minibar and operational stock

- Management configures stock items, units, reorder levels and active storage locations before movements are posted.
- Post every supplier receipt, issue, waste, adjustment and transfer through **Operational Stock**. Never edit the calculated balance.
- Use the generated idempotency key when retrying an interrupted submission; reuse with different details is rejected.
- A transfer creates equal outgoing and incoming ledger entries. Confirm both locations and quantity before posting.
- Housekeeping is limited to linen and housekeeping supplies; reception is limited to minibar/other front-office stock. Management controls receipts and adjustments.
- The system rejects an issue, waste or transfer that would make a location negative. Investigate physical/count differences and have management post a reasoned adjustment.
- Review highlighted balances at or below reorder level during shift handover.
