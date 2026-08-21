# Guest and Portal Roles Access Guide

This guide details the user flows for public guests on the website and defines the exact access controls, permissions, and constraints for each portal role (Admin, Manager, Accountant, Receptionist, Housekeeping).

---

## 1. Public Guest Flow (Website)

Public guests visit the website to find, review, and book hotel rooms directly without pre-registering an account.

### Step 1: Room Search
- Guests input their desired **Check-In Date**, **Check-Out Date**, **Adults** count, and **Children** count on the homepage search form.
- The system checks real-time availability by excluding any rooms with overlapping bookings, active staff maintenance blocks, or temporary holding states.

### Step 2: Room Selection & Details
- The guest is redirected to the `/rooms/` page showing available rooms that meet their capacity requirements.
- Clicking **More Details** takes the guest to the Room Details view where they can read comprehensive room amenities, view the gallery, and select optional enhancing services (extras).

### Step 3: Booking Request & OTP Verification
- The guest enters their personal information (Name, Email, Phone, and Special Requests) directly in the reservation form on the Room Details page and clicks **Book Room**.
- The system generates an itemized price quote (held for 10 minutes) and sends a secure 6-digit **verification OTP** instantly via Brevo to the guest's email.
- The guest enters the OTP on the validation page. Upon success, the system automatically:
  1. Spins up a Guest profile.
  2. Creates the Reservation record.
  3. Registers a Folio containing itemized charges.
  4. Redirects the guest to their personal dashboard.

---

## 2. Staff Portal Roles & Permissions Matrix

Staff members log in via `/portal/sign-in/` and have access partitioned by their assigned roles.

| Feature / Action | Admin | Manager | Accountant | Receptionist | Housekeeping | Guest |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Rooms & Settings** | Full | Full | Read-Only | Read-Only | Read-Only | Read-Only |
| **Check-in / Check-out** | Yes | Yes | No | Yes | No | No |
| **Record Payment** | Yes | Yes | Yes | Yes | No | No |
| **Refund Payment** | Yes | Yes | Yes | No | No | No |
| **Create Financial Correction** | Yes | Yes | Yes | No | No | No |
| **Update Housekeeping Status** | Yes | Yes | No | Yes | Yes | No |
| **WhatsApp Contact Configuration** | Yes | No | No | No | No | Public WhatsApp action |
| **Expenditure Submission** | Yes | Yes | No | No | No | No |
| **Expenditure Review & Payment** | Yes | No | No | Yes | No | No |
| **Ledger, Reconciliation & Tax Controls** | Yes | View | No | Yes | No | No |
| **Delete Payments / Receipts** | **NO** | **NO** | **NO** | **NO** | **NO** | **NO** |

---

## 3. Detailed Role Access Rules

### 👤 Admin
- **Full Control**: Complete management of system configuration, room inventory, price rules, and user accounts.
- **Audit & Analytics**: Access to all security audit logs, reconciliation outputs, and financial dashboards.
- **Escalations**: Ability to approve cancel/void requests initiated by receptionists.

### 👤 Manager
- **Operations Control**: Similar capabilities to Admin, including inventory blocking, booking overrides, and approving shift discrepancies.
- **Financial Authorization**: Can authorize manual cash movements, refunds, and adjustments.

### 👤 Accountant
- **Financial Oversight**: Full access to financial ledgers, Z-reports, and terminal shift summaries.
- **Adjustments & Credits**: Authorized to record refunds and create financial corrections (debit adjustments and credit notes) on folios.
- **Immutable Constraints**: Like all roles, Accountants are blocked from deleting any financial records.

### 👤 Receptionist
- **Front-Desk Tasks**: Handles guest arrivals, departures, walk-in bookings, and logging service orders.
- **Cashiering**: Opens and closes their terminal cashier shift, counting cash and registering manual payments.
- **Payment Constraint**: Receptionists **cannot** modify or delete completed payments, receipts, or invoices.
- **Cancellation Request Flow**: If a payment or transaction needs to be cancelled or voided, the receptionist cannot perform it directly. They must send a request to the Admin/Manager to authorize and process the state change.

### 👤 Housekeeping
- **Cleanliness Log**: Access is restricted to the room status dashboard to mark rooms as clean, dirty, or out-of-order.
- **Constraints**: No access to financial, billing, guest booking, or system settings directories.

---

## 4. Immutable Records and Financial Controls

To maintain a compliant audit trail suitable for hotel operations, the system enforces strict database-level protection against record tampering:

1. **Compensating Entries Only**: If a payment or charge is entered incorrectly, it cannot be deleted or modified. The discrepancy must be resolved by posting a compensating entry (e.g., a credit note or adjustment) so all changes are recorded.
2. **Deletions Prohibited**: The `delete()` method is overridden on critical database tables (`Payment`, `Receipt`, `Invoice`, `Folio`, and `FolioEntry`) to raise a `ValidationError` and block deletion attempts:
   ```python
   def delete(self, *args, **kwargs):
       raise ValidationError('This record is immutable and cannot be deleted.')
   ```
3. **Audit Trail**: Every payment registration, refund authorization, and cashier shift closure triggers an automated audit entry logging the timestamp, action details, and the authorizing staff user profile.
