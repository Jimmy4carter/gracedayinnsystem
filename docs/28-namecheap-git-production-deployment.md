# Namecheap Git Production Deployment Runbook

## Release model

`production` is the only deployable branch. Development work can happen elsewhere, but a Namecheap release must be committed to and pushed from `production`.

```text
local production -> GitHub origin/production -> cPanel managed clone -> .cpanel.yml -> Passenger
```

The repository includes:

- `.cpanel.yml`, the cPanel deployment entry point;
- `deploy/namecheap_deploy.sh`, the repeatable deployment hook;
- `deploy/namecheap_preflight.sh`, a production configuration and migration check;
- `passenger_wsgi.py`, the WSGI startup file required by Namecheap shared hosting;
- WhiteNoise static-file serving for collected CSS, JavaScript, fonts, and images.

Namecheap shared hosting supports WSGI Python applications. GraceDay Inn therefore uses a direct WhatsApp action for public messaging and does not require WebSockets, Redis, Daphne, or an ASGI process.

## 1. Prepare the remote repository

Push the deployable branch to GitHub:

```bash
git switch production
git push -u origin production
```

Keep `main` protected if it remains the integration branch. Never merge an unreviewed change directly on the server.

## 2. Create the cPanel-managed clone

In **cPanel > Files > Git Version Control**:

1. Select **Create** and enable **Clone a Repository**.
2. Enter the GitHub clone URL.
3. Set the repository path to `/home/CPANEL_USERNAME/gracedayinnsystem`.
4. Create the repository.
5. Open cPanel Terminal and select the deployment branch once:

```bash
cd /home/CPANEL_USERNAME/gracedayinnsystem
git fetch origin production
git switch production
git branch --set-upstream-to=origin/production production
```

The cPanel checkout must stay clean. Do not edit tracked application files through File Manager or cPanel editors. Runtime files are ignored by Git.

For a private GitHub repository, add the cPanel account's SSH public key to GitHub as a read-only deploy key and use the SSH clone URL.

## 3. Create the Namecheap Python app

In **cPanel > Setup Python App**, create the application with:

| Field | Value |
| --- | --- |
| Python version | 3.12 (3.11 is also supported) |
| Application root | `gracedayinnsystem` |
| Application URL | `gracedayinn.com` |
| Startup file | `passenger_wsgi.py` |
| Entry point | `application` |

The deployment hook automatically discovers the cPanel virtual environment at `/home/CPANEL_USERNAME/virtualenv/gracedayinnsystem/VERSION/bin/python`. If the application root differs, make `GRACEDAY_PYTHON` available to the deployment process with that Python binary's absolute path.

## 4. Configure secrets outside Git

Use **Setup Python App > Environment variables** or an ignored `/home/CPANEL_USERNAME/gracedayinnsystem/.env` file. Copy variable names from `.env.example`, replace every placeholder, and never commit `.env`.

Required production groups are:

- Django: `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`;
- MySQL: `DATABASE_URL=mysql://USER:PASSWORD@127.0.0.1:3306/DATABASE`;
- persistent files: `MEDIA_ROOT=/home/CPANEL_USERNAME/gracedayinn_media` and an application-local `STATIC_ROOT`;
- staff security: `MFA_ENCRYPTION_KEY` and the six `DEFAULT_*_PASSWORD` values;
- sender: `DEFAULT_FROM_EMAIL=noreply@gracedayinn.com` and `SERVER_EMAIL=noreply@gracedayinn.com`;
- Brevo REST (recommended): `EMAIL_DELIVERY_PROVIDER=brevo` and a new production `BREVO_API_KEY`;
- Brevo webhook verification: a new random `BREVO_WEBHOOK_TOKEN`.
- public contact: `WHATSAPP_NUMBER` (country code plus digits) and `WHATSAPP_DEFAULT_MESSAGE`.

SMTP delivery remains available, but an SMTP key is not a Brevo REST API key. Even in SMTP mode, configure a REST API key because contact synchronization and reporting use the API.

The SMTP key shared during development must be rotated before production. Store the replacement only in cPanel or the ignored server `.env`; Git history is not a secret store.

## 5. Database and persistent media

Create a MySQL/MariaDB database and user through cPanel, grant that user all privileges on the application database, and use the cPanel-prefixed database and username in `DATABASE_URL`.

Uploaded room, billboard, and protected financial evidence must survive releases. Keep `MEDIA_ROOT` outside the repository. Configure domain/LiteSpeed mappings only for approved public image subdirectories. Explicitly deny `/media/private/`; expenditure evidence is downloaded only through the authenticated portal endpoint. Do not expose private guest identity documents or financial evidence through a public media mapping.

Take a cPanel database backup before any release that contains schema or financial-ledger migrations. Code rollback does not reverse a migrated database automatically.

## 6. First deployment

Activate the exact virtual-environment command shown by **Setup Python App**, then run:

```bash
cd /home/CPANEL_USERNAME/gracedayinnsystem
bash deploy/namecheap_deploy.sh
```

The hook installs requirements, runs Django's production and migration-drift checks, collects static assets, previews and applies migrations, creates the database cache table, verifies the standard accounts, runs launch readiness and full reconciliation, and touches `tmp/restart.txt` to restart Passenger.

If cPanel cannot auto-detect the virtual environment:

```bash
GRACEDAY_PYTHON=/home/CPANEL_USERNAME/virtualenv/gracedayinnsystem/3.12/bin/python bash deploy/namecheap_deploy.sh
```

## 7. Routine release workflow

```bash
git switch production
git status
git add <reviewed-files>
git commit -m "Describe the production release"
git push origin production
```

Then in **cPanel > Git Version Control > Manage > Pull or Deploy**:

1. Click **Update from Remote**.
2. Click **Deploy HEAD Commit**.
3. Confirm the deployed SHA and deployment output.

This is the reliable pull-deployment path. A local commit alone cannot reach a server; it must be pushed and deployed.

### Optional direct push deployment

cPanel also supports push deployment. After SSH access is enabled, add the SSH clone URL shown by the cPanel-managed repository as a second remote:

```bash
git remote add cpanel ssh://CPANEL_USERNAME@SERVER_HOST:21098/home/CPANEL_USERNAME/gracedayinnsystem
git push cpanel production
```

Use the exact URL shown in cPanel. With push deployment enabled, cPanel runs the committed `.cpanel.yml` automatically. Keep `origin` as GitHub and `cpanel` as the production server; always push the `production` branch explicitly.

## 8. Cron and operational checks

Add a five-minute cPanel cron job through the committed wrapper. The wrapper discovers the virtual environment and explicitly selects production settings. cPanel Python App variables are not guaranteed to be inherited by Git deployment hooks or cron, so keep the same secrets in the ignored project `.env` (mode `600`) unless your hosting environment explicitly exports them to both processes:

```cron
*/5 * * * * /bin/bash /home/CPANEL_USERNAME/gracedayinnsystem/deploy/namecheap_cron.sh >> /home/CPANEL_USERNAME/graceday_cron.log 2>&1
```

After every release verify:

- `/` and `/portal/sign-in/` return successfully over HTTPS;
- `/static/` assets load and a public room image loads from persistent media;
- a test reservation can proceed through invoice and payment state;
- a Brevo test email appears in the portal email log and reaches the recipient;
- the WhatsApp action opens the verified hotel number;
- manager expenditure submission, accountant approval/payment, Excel export and balanced journal posting pass a smoke test;
- the deployed SHA in cPanel matches `origin/production`;
- cron processing is current and has no repeated errors.

## 9. Rollback

For a code-only rollback, revert the bad commit on `production`, push the revert, and deploy it normally:

```bash
git switch production
git revert BAD_COMMIT_SHA
git push origin production
```

For a schema-changing release, restore only from a verified pre-release database backup and coordinate the matching code version. Never use a hard reset on the production repository as the normal rollback procedure.
