# GraceDay TV reception billboard

## Opening the display

Open `/billboard/` on the reception display, then press `F` or use the Fullscreen control. The programme schedules a varied sequence of brand moments, room spotlights, services, promotions, questions, local information, reviews, announcements, videos and QR calls to action. A room is selected from the available inventory for each room slot instead of displaying every room in sequence.

Keyboard controls:

- `Right Arrow`: next scene
- `Left Arrow`: previous scene
- `Space`: pause or resume
- `F`: fullscreen
- `R`: rebuild and restart the programme

Controls appear when the mouse moves and then hide for an uninterrupted TV presentation.

## Managing broadcast content

Administrators manage **Billboard content** in Django admin. Each item supports:

- a content type, priority, layout and transition;
- headline, supporting copy, icon, image, video and fallback image;
- display duration and order;
- optional call to action;
- activation and scheduled start/end times.

Use **Important** only for operational notices that must be inserted frequently. Time-sensitive offers should always have an end time. Attach a fallback image to video content so the scene remains useful if playback fails.

The public content sources are also used automatically: active promotions, sellable room inventory and galleries, sent announcements, published FAQs, approved testimonials and published local-guide entries.

## Resilience and operations

- Broken images and videos fall back to a branded visual instead of leaving an empty screen.
- The core programme remains readable if the remote animation library cannot load; motion is progressively enhanced when it is available.
- The display checks for published billboard changes every ten minutes and refreshes at a brand break.
- Browser visibility pauses playback and videos to avoid needless resource use.
- Use a wired or stable Wi-Fi connection for uploaded video media. Prefer short, web-optimized MP4 files without essential audio.
- The status feed is available at `/billboard/?status=1` for lightweight content-version monitoring.

## Release checks

Run:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test apps.frontend.tests_public
```

Before reception use, review at 1920×1080 for at least one full programme and confirm that the QR code opens the public rooms page from a phone.
