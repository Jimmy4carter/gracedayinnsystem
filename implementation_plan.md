# Implementation Plan - GraceDay Inn System Refinement

This plan details the refinements and backend functional enhancements for GraceDay Inn, specifically covering role-based access control, a secure guest booking email-verification flow, and a fully functional operations dashboard.

## User Review Required

> [!IMPORTANT]
> The email verification system is configured to use Django's console email backend (`django.core.mail.backends.console.EmailBackend`) for development. When a guest submits a booking, the verification code and generated password will print directly to the server's console.
> 
> Password generation for guest accounts will enforce the specified criteria: starting with `GDI` and containing exactly 8 alphanumeric characters in total (e.g. `GDI` + 5 random lowercase letters/digits).

## Proposed Changes

---

### Component: Accounts & Authentication

#### [MODIFY] [decorators.py](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/decorators.py)
- Import `role_required` in `views.py` if not already. Ensure that roles can be set and checked on view entry.

#### [MODIFY] [views.py](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/views.py)
- Import `role_required` decorator.
- Update view routing checks and decorate views:
  - `portal_guests` -> `@role_required({'admin', 'manager', 'receptionist'})`
  - `portal_reports`, `portal_reports_export_csv`, `portal_reports_export_pdf` -> `@role_required({'admin', 'manager'})`
  - `portal_housekeeping`, `portal_housekeeping_action` -> `@role_required({'admin', 'manager', 'receptionist', 'housekeeping'})`
- Implement `portal_dashboard` view to query real database metrics, trends, and recent logs instead of executing an immediate logout.
- Add `portal_verify_booking` view to handle the email verification code input, guest user registration (with auto-generated 8-character password starting with `GDI`), reservation creation, and session logging in.

#### [MODIFY] [urls.py](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/urls.py)
- Add route for `portal/verify-booking/` mapped to `views.portal_verify_booking`.

---

### Component: Public & Portal Templates

#### [MODIFY] [base_portal.html](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/templates/base_portal.html)
- Dynamically render menu items in the sidebar using Django template conditionals `{% if request.user.role in ... %}`:
  - **Guests**: Admin, Manager, Receptionist
  - **Housekeeping**: Admin, Manager, Receptionist, Housekeeping
  - **Reports**: Admin, Manager

#### [MODIFY] [reservations.html](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/templates/portals/reservations.html)
- Display reservation action buttons (`Confirm`, `Check In`, `Check Out`, `Cancel`) conditionally based on the reservation's current status and the user's role, avoiding broken operations.

#### [MODIFY] [housekeeping.html](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/templates/portals/housekeeping.html)
- Conditionally render housekeeping task transition actions (`Start`, `Complete`, `Verify`) based on task status.

#### [MODIFY] [services.html](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/templates/portals/services.html)
- Conditionally render service order transition actions (`Confirm`, `Start`, `Complete`, `Cancel`) based on order status.

#### [NEW] [verify-booking.html](file:///c:/Users/User/Documents/GitHub/Graceinn/gracedayinnsystem/apps/frontend/templates/portals/verify-booking.html)
- Create a new template for the verification page where guests can enter the 6-digit code sent to their email to complete their booking.

---

## Verification Plan

### Automated Tests
- Run Django check to verify syntactical correctness:
  ```powershell
  .\.venv\Scripts\python manage.py check
  ```
- Run standard unit tests for frontend and account apps:
  ```powershell
  .\.venv\Scripts\python manage.py test
  ```

### Manual Verification
1. **Booking Verification**:
   - Go to the public homepage, submit a room booking with a guest email.
   - Observe the verification code printed in the terminal console.
   - Enter the verification code on the redirect page.
   - Verify that:
     - The booking is created successfully in the backend.
     - A user account is created with a password starting with `GDI` (total 8 characters).
     - The user is automatically logged in and redirected to the dashboard.
2. **Role-Based Access**:
   - Log in with a `guest` user and confirm they cannot see restricted menu items (e.g. Guests, Housekeeping, Reports). Attempting to visit those URLs directly should redirect to dashboard with an error.
   - Log in with `admin`/`manager`/`housekeeping` users and verify that the sidebar and action buttons dynamically adapt to their roles.
