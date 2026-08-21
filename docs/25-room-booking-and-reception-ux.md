# Room, booking, and reception UX update

- Dashboard charts use a fixed-height wrapper so Chart.js cannot grow the document indefinitely. A previous chart instance is destroyed before re-rendering.
- The first cashier visit provisions `Front Desk 1` when no active terminal exists. Production should rename/configure it and add additional terminals through the admin/API surface.
- Room creation and editing show amenities as individual checkboxes.
- Room records accept a cover image plus multiple additional gallery images. Portal room details and public room pages display those galleries.
- Room categories (`RoomType`) now have unique slugs, which can be used for visitor-friendly category filters and SEO links.
- Staff confirmation requires at least 50% of the invoice total to be paid; the user is redirected directly to payment when the requirement is not met.
- Availability search continues to exclude overlapping reservations, active quote holds, and inventory blocks before showing results.

The remaining booking enhancement is a dedicated guest-facing quote checkout page that collects an existing email or creates a guest profile, displays the full price breakdown, converts the quote into a pending reservation, and sends the welcome/invoice/confirmation sequence. The underlying quote, reservation, invoice, and payment services already exist; that page should be the next isolated UX slice rather than duplicating booking logic in templates.
