# WhatsApp public contact

GraceDay Inn uses a direct WhatsApp action instead of an embedded live-chat or WebSocket service. This is compatible with Namecheap shared hosting and avoids operating a second real-time support queue.

## Configuration

Set these cPanel Python application environment variables:

```env
WHATSAPP_NUMBER=2347080076496
WHATSAPP_DEFAULT_MESSAGE=Hello GraceDay Inn, I would like help with a reservation.
```

The number must contain the country code and 8–15 digits. Do not include a plus sign, spaces, or the local leading zero.

An administrator can change the same values from **Portal → System Settings → Public WhatsApp contact**. The database setting takes precedence over the environment default and the change is written to the tamper-evident audit log.

## Launch verification

1. Open the public home page on desktop and mobile.
2. Select **WhatsApp us**.
3. Confirm `wa.me` opens the intended hotel account with the pre-filled greeting.
4. Confirm `/chat/start/`, `/portal/chat/`, and `/ws/chat/` are unavailable.

Historical chat database tables remain read-only-compatible so an upgrade does not destroy old records. No public, portal, alert, or WebSocket route uses them.
