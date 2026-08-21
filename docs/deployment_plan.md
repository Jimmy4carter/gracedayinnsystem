# Deployment Plan — Namecheap cPanel Shared Hosting (MySQL + WSGI Passenger)

This document provides a step-by-step guide to deploying the GraceDay Inn booking system to Namecheap shared hosting from the repository's `production` branch. It uses cPanel Git Version Control, Passenger WSGI, MySQL, and cPanel cron; routine releases do not use File Manager.

---

## Pre-Requisites & Checklist

- [ ] A Namecheap shared hosting account with cPanel access.
- [ ] SSH access enabled on your Namecheap account (you can request this from Namecheap support or enable it under cPanel).
- [ ] A Brevo account with an API key, an authenticated `gracedayinn.com` sending domain, and verified `noreply@gracedayinn.com` sender.
- [ ] A verified WhatsApp Business number for the public contact action.

---

## Step 1: Create the MySQL Database
1. Log into your Namecheap cPanel.
2. Search for and open the **MySQL® Database Wizard**.
3. **Step 1: Create A Database**: Name your database (e.g., `graceday_db`) and click **Next Step**.
4. **Step 2: Create Database Users**: Enter a database username (e.g., `graceday_user`) and generate a strong password. Note the database name, username, and password. Click **Create User**.
5. **Step 3: Add User to the Database**: Select **ALL PRIVILEGES** and click **Next Step** / **Make Changes**.

---

## Step 2: Set Up the Python Application
1. In cPanel, search for and open **Setup Python App**.
2. Click **Create Application**.
3. Configure the following:
   - **Python Version**: Select **3.11**, **3.12**, or **3.13**. Python 3.11 is the conservative shared-hosting choice.
   - **Application root**: Enter the folder name where your files will live relative to your home directory (e.g., `gracedayinnsystem`).
   - **Application URL**: Select your domain name (e.g., `gracedayinn.com`).
   - **Application startup file**: Enter `passenger_wsgi.py`.
   - **Application Entry point**: Leave blank.
4. Click **Create** (this generates the folder and virtual environment).

---

## Step 3: Connect cPanel Git Version Control

1. Push the local `production` branch to GitHub: `git push -u origin production`.
2. In cPanel, open **Git Version Control** and choose **Create**.
3. Enable **Clone a Repository**, enter the GitHub clone URL, use `/home/CPANEL_USERNAME/gracedayinnsystem` as the repository path, and create the repository.
4. In cPanel Terminal, open the cloned repository and run `git switch production` followed by `git branch --set-upstream-to=origin/production production` once.
5. Confirm that `.cpanel.yml`, `passenger_wsgi.py`, `manage.py`, and `requirements.txt` are at the repository root.
6. In **Setup Python App**, use `gracedayinnsystem` as the application root, `passenger_wsgi.py` as the startup file, and `application` as the entry point.

For each later release: commit on `production`, push to `origin production`, click **Update from Remote**, then **Deploy HEAD Commit**. The checked-in `.cpanel.yml` runs `deploy/namecheap_deploy.sh`; File Manager is not part of the release process. See `docs/28-namecheap-git-production-deployment.md` for the full runbook and direct-push option.

---

## Step 4: Configure Production Environment Variables
In cPanel **Setup Python App**, scroll down to the **Configuration files** and **Environment variables** section. Add the following environment variables:

| Variable Name | Example Value | Description |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `gracedayinn.settings.prod` | Forces production settings checks. |
| `SECRET_KEY` | `at-least-50-chars-random-long-secret-key-1234` | A secure, unique random string. |
| `ALLOWED_HOSTS` | `gracedayinn.com,www.gracedayinn.com` | Your production domains. |
| `DATABASE_URL` | `mysql://graceday_user:PASSWORD@127.0.0.1:3306/graceday_db` | Your MySQL connection string. |
| `CSRF_TRUSTED_ORIGINS` | `https://gracedayinn.com,https://www.gracedayinn.com` | Trusted origins for form safety. |
| `CORS_ALLOWED_ORIGINS` | `https://gracedayinn.com` | Trusted origins for API calls. |
| `EMAIL_DELIVERY_PROVIDER` | `brevo` | Recommended REST delivery with provider event logging. |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | Enables Django SMTP delivery. |
| `EMAIL_HOST` | `smtp-relay.brevo.com` | Brevo SMTP relay host. |
| `EMAIL_PORT` | `587` | Brevo TLS submission port. |
| `EMAIL_HOST_USER` | Brevo SMTP login | Store only in cPanel/server `.env`, never Git. |
| `EMAIL_HOST_PASSWORD` | Brevo SMTP key | Store only in cPanel/server `.env`, never Git. |
| `EMAIL_USE_TLS` | `True` | Encrypts SMTP transport. |
| `BREVO_API_KEY` | `xkeysib-...` | Required for delivery, contacts, and reporting; create a new production key. |
| `BREVO_WEBHOOK_TOKEN` | `strong-32-character-random-secret` | For security validation. |
| `WHATSAPP_NUMBER` | `2347080076496` | Hotel WhatsApp number with country code, digits only. |
| `WHATSAPP_DEFAULT_MESSAGE` | `Hello GraceDay Inn, I would like help with a reservation.` | Pre-filled public greeting. |
| `MFA_ENCRYPTION_KEY` | `strong-32-character-random-secret` | For staff login security. |
| `HOTEL_CURRENCY` | `NGN` | Default currency code. |
| `TIME_ZONE` | `Africa/Lagos` | Hotel timezone. |
| `DEFAULT_FROM_EMAIL` | `noreply@gracedayinn.com` | Verified Brevo transactional sender. |
| `DEFAULT_ADMIN_PASSWORD` | unique generated secret | Initial `admin@gracedayinn.com` account. |
| `DEFAULT_MANAGER_PASSWORD` | unique generated secret | Initial `manager@gracedayinn.com` account. |
| `DEFAULT_RECEPTION_PASSWORD` | unique generated secret | Initial `reception@gracedayinn.com` account. |
| `DEFAULT_ACCOUNTANT_PASSWORD` | unique generated secret | Initial `accounts@gracedayinn.com` account. |
| `DEFAULT_HOUSEKEEPING_PASSWORD` | unique generated secret | Initial `housekeeping@gracedayinn.com` account. |
| `DEFAULT_INFO_PASSWORD` | unique generated secret | Initial `info@gracedayinn.com` test/guest account. |

Click **Save** or **Update** after adding each variable.

---

## Step 5: First Deployment
1. Open your terminal and connect to your hosting account via SSH:
   ```bash
   ssh cpanel_username@your_server_ip -p 21098
   ```
2. Activate the virtual environment generated by cPanel (copy the exact command shown at the top of your **Setup Python App** page in cPanel):
   ```bash
   source /home/cpanel_username/virtualenv/gracedayinnsystem/3.11/bin/activate
   ```
3. Navigate to the project root directory:
   ```bash
   cd ~/gracedayinnsystem
   ```
4. Run the repository deployment hook; future cPanel deployments run this automatically:
   ```bash
   bash deploy/namecheap_deploy.sh
   ```

---

## Step 6: What the Automated Hook Runs

The checked-in hook runs the following operations in order on every release:

1. **Database Migrations** (creates all MySQL tables):
   ```bash
   python manage.py migrate
   ```
2. **Reconcile System** (initializes base database configurations):
   ```bash
   python manage.py reconcile_system
   ```
3. **Ensure deployment users** (idempotently creates or verifies every standard account):
   ```bash
   python manage.py ensure_default_users
   ```
4. **Create Cache Table** (creates the shared database cache table required by WSGI Passenger):
   ```bash
   python manage.py createcachetable
   ```
5. **Collect Static Files** (gathers CSS/JS files into the public directory):
   ```bash
   python manage.py collectstatic --noinput
   ```

---

## Step 7: Set Up the Background Task Scheduler
To process automated tasks (outbound email queue, Brevo contact synchronization, hold cleanups) without running a persistent daemon process, configure a cPanel cron job:

1. In cPanel, search for and open **Cron Jobs**.
2. Under **Add New Cron Job**:
   - **Common Settings**: Select **Once Per Five Minutes** (`*/5 * * * *`). Namecheap shared-hosting policy does not allow intervals shorter than five minutes.
   - **Command**: Set the command to run `run_scheduled_jobs` using the absolute path to your virtual environment's python binary:
     ```bash
     /bin/bash /home/cpanel_username/gracedayinnsystem/deploy/namecheap_cron.sh >> /home/cpanel_username/graceday_cron.log 2>&1
     ```
     *(Be sure to replace `cpanel_username` and version number `3.11` with your actual hosting path and Python version)*.
3. Click **Add New Cron Job**.

---

## Step 8: Start and Restart the App
1. Go back to cPanel **Setup Python App**.
2. Click **Restart** on your application.
3. Visit your website URL. Confirm the site uses the MySQL database and the WhatsApp action opens the verified hotel number with the configured greeting.

---

## Shared-hosting constraints and launch checks

- Namecheap shared hosting serves the Django application through WSGI and `passenger_wsgi.py`. The retired live-chat/WebSocket runtime is not part of production; the public support action opens the configured WhatsApp Business number and inquiries continue through the normal contact workflow.
- Run `bash deploy/namecheap_preflight.sh` after environment variables are configured and before the first live release.
- Run `python manage.py test apps.billing.tests_vat apps.notifications.tests` before packaging a release.
- Confirm `/static/` maps to `collected_static` in the Python App configuration or web root, and `/media/` points to persistent storage outside each release archive.
- Do not upload `.env`, local databases, logs, backup archives, generated credentials, or API keys.
- After DNS is live, authenticate `gracedayinn.com` in Brevo and verify SPF/DKIM before enabling production sending.
- Use a five-minute cron and periodically review `/portal/` email delivery logs for deferred, bounced or suppressed messages.
