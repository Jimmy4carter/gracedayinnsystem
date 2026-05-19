# Graceday Inn System

Graceday Inn System is a Django-based hotel management platform with two major parts:

- a public-facing hotel website in `apps/frontend/`
- a back-office style management system exposed through Django apps and API routes

The project is organized around hotel operations such as rooms, reservations, billing, payments, services, housekeeping, notifications, and account management.

## What is in the project

- `apps/accounts/` for user profiles and authentication-related work
- `apps/rooms/` for room records and room-related API views
- `apps/reservations/` for booking and reservation flows
- `apps/billing/` and `apps/payments/` for invoices and payment handling
- `apps/services/`, `apps/housekeeping/`, and `apps/notifications/` for operational workflows
- `apps/frontend/` for the public site and hotel-style pages
- `gracedayinn/` for project settings, URL routing, ASGI, and WSGI entry points

## Public site pages

The frontend already includes templates for:

- home / landing page
- login and registration
- dashboard
- rooms, reservations, and reservation details
- guests
- billing and invoice details
- payments
- services
- restaurant
- housekeeping
- reports

## Current gaps to be aware of

This codebase has the structure of a hotel platform, but several parts still need product-level polish before it feels complete:

- many frontend pages are still template shells and need real content, stronger layout hierarchy, and more hotel-specific copy
- the homepage still relies on placeholder-style data in places and needs richer imagery and a stronger luxury brand presentation
- the public site needs a more detailed booking journey, better room storytelling, and stronger calls to action
- the visual design is still closer to a generic glassmorphism template than a finished hotel brand
- there is no documented production deployment flow in this repository yet
- tests exist as app placeholders, but there is no documented end-to-end test strategy in the README yet

## What to look out for

- SQLite is the default database in local development, so anything production-related should be migrated to a real hosted database
- `DEBUG` defaults to `True` unless overridden in environment variables
- secrets are expected from environment variables via `python-decouple`; do not hardcode production values
- email is configured to use the console backend by default, so outbound email will print to the terminal during local development
- static files are served from `apps/frontend/static/` in development and collected into `staticfiles/` for deployment
- CORS is currently limited to localhost origins in settings

## Local setup

### Prerequisites

- Python 3.11 or compatible Django 4.2 environment
- `pip`

### Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Configure environment variables

Create a `.env` file in the project root with values such as:

```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@gracedayinn.com
```

### Database setup

```bash
python manage.py migrate
```

If you want an admin user for local testing:

```bash
python manage.py createsuperuser
```

### Run the project

```bash
python manage.py runserver
```

Open the site at `http://127.0.0.1:8000/`.

## Project routes

- `/` public landing page
- `/login/` sign-in page
- `/register/` registration page
- `/dashboard/` dashboard page
- `/rooms/` room listing page
- `/reservations/` reservation listing page
- `/reservations/new/` new reservation page
- `/guests/` guest list page
- `/billing/` billing page
- `/payments/` payments page
- `/services/` services page
- `/restaurant/` restaurant page
- `/housekeeping/` housekeeping page
- `/reports/` reports page
- `/admin/` Django admin

## Recommended next improvements

- replace the generic public-site styling with a strong hotel brand system
- add high-quality photography and room imagery across the landing pages
- connect the frontend templates to real room, reservation, and offer data
- add a clear booking funnel with availability checks and confirmation states
- document API endpoints and environment variables in more detail
- add tests for the most important booking, payment, and staff workflows
