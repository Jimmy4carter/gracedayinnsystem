# Design System and Experience Plan

## Experience direction

The public website should feel warm, calm, trustworthy and distinctly GraceDay Inn—not like a reskinned admin theme. Operational portals should prioritize speed, clarity and error prevention over decorative effects. Both surfaces share brand foundations but use different density and interaction patterns.

## Brand and visual foundation

- Confirm logo usage, photography direction, color accessibility, typography licenses, icon system and tone of voice.
- Define semantic tokens for background, surface, text, border, brand, success, warning, danger, focus and data visualization.
- Define spacing, radius, elevation, motion, content widths and responsive breakpoints.
- Use motion sparingly for page/state continuity and respect `prefers-reduced-motion`.
- Replace untraceable placeholder/vendor imagery and archive/source bundles with an approved asset pipeline.

## Public website patterns

- Strong photo-led hero with immediately usable availability search.
- Room cards communicate capacity, bed, key amenities, price basis and cancellation/deposit cue.
- Room detail combines gallery, description, amenities, accessibility facts, policy, price breakdown and persistent booking action.
- Booking uses a visible stepper, saved progress, inline validation, clear total and no surprise charges.
- Empty/no-availability results offer alternate dates/rooms or inquiry—not a dead end.
- Contact, inquiry and chat entry points remain visible without competing with booking.

## Portal patterns

- Role-specific home and navigation; do not show unusable modules.
- Global command/search for guest, reservation, room, folio and payment reference.
- Today board uses stable status language and accessible color plus icons/text.
- Tables support saved filters, column choice, pagination, export permission and responsive detail drawers.
- State-changing actions show consequence, required reason/approval and resulting state.
- Money/date/status presentation is consistent and local-property aware.
- Forms autosave drafts where safe, prevent duplicate submit and preserve user input after validation errors.
- Success messages include the created reference and next action; errors explain recovery without leaking internals.

## Front-desk ergonomics

- Common workflow target: guest lookup and new walk-in begin within one interaction from the dashboard.
- Keyboard shortcuts must avoid browser/assistive-technology conflicts and be documented in the UI.
- Large click targets, predictable tab order, scanner-friendly inputs and minimal modal nesting.
- Keep reservation summary, room readiness and folio balance visible through check-in/out.
- Printing shows a preview/status, printer profile and retry; payment success remains unambiguous if printing fails.

## Management portal design

- Headline KPIs show formula tooltip, comparison period, last refresh and drill-down.
- Use charts only when they reveal trend/composition; tables carry exact values.
- Filters are consistent across dashboard/report/query and preserved in shared links where authorized.
- Exceptions and overdue queries appear before decorative analytics.
- Report snapshots clearly state property, business date, timezone, currency and generation time.

## Accessibility and content standards

- WCAG 2.2 AA target: contrast, keyboard, visible focus, semantics, labels, errors, landmarks and screen-reader announcements.
- No status/action communicated by color alone; charts include accessible summaries/tables.
- Plain, respectful language; explain hotel terms to guests but retain efficient staff terminology.
- Format phone, address, currency and dates consistently; never rely on ambiguous numeric dates.
- Images require meaningful alt text or explicit decorative treatment; galleries support keyboard and touch.

## Design delivery workflow

1. Audit content and analytics; interview representative guests and each staff role.
2. Map critical journeys and low-fidelity prototypes before visual polish.
3. Build coded component inventory/story pages in Django templates.
4. Test booking and front-desk prototypes with real users/hardware.
5. Implement page families with analytics and accessibility acceptance criteria.
6. Run visual regression and responsive QA before each release.

## Page-level acceptance checklist

- Real data plus loading, empty, error, forbidden and success states.
- Mobile/tablet/desktop behavior approved for the target role.
- Keyboard and screen-reader flow tested for critical actions.
- Performance budget met and images appropriately sized/lazy-loaded.
- Authorization is enforced server-side; UI accurately reflects permitted actions.
- Analytics excludes sensitive values and captures agreed funnel/operational events.
- Content and imagery approved by the hotel owner.
