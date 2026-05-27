# Kairix Judgenburn

Live-event judging, run control, scoring, queue display, public results, and OBS graphics for burnout competitions.

## Requirements

- Git
- Docker Desktop on Windows/macOS, or Docker Engine with Compose on Linux
- A modern browser for admin, judge, public display, and OBS pages

## Quick Start

Clone the project onto the event computer, then run one command from the project folder.

Windows PowerShell:

```powershell
.\run.ps1
```

If Windows blocks script execution, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Linux, macOS, or a server shell:

```bash
sh ./run.sh
```

The first run copies `.env.example` to `.env`, builds the Docker image, starts PostgreSQL and the web service, then waits for the health check.

Default local URLs:

- Home / login: `http://localhost:7080/`
- Admin dashboard: `http://localhost:7080/admin`
- Judge page: `http://localhost:7080/judge`
- Graphics control: `http://localhost:7080/gfx-control`
- OBS overlay: `http://localhost:7080/obs-overlay`
- Competitor queue: `http://localhost:7080/queue`
- Public display: `http://localhost:7080/public`
- Recovery page: `http://localhost:7080/recovery`

Optional isolated public display container:

```bash
docker compose --profile public up -d public
```

That serves only the public display and queue pages on `http://localhost:7081/`, proxying the safe `/api/public/snapshot` from the main app. For a cloud-hosted public display, deploy the same image with the command `uvicorn app.public_app:app --host 0.0.0.0 --port 8080 --proxy-headers` and set `PUBLIC_UPSTREAM_URL` to the main judging server URL.

## Portainer Git Deployment

Use Portainer's Git repository stack option and point it at this repository. Set the compose path to:

```text
docker-compose.portainer.yml
```

The Portainer compose builds the web and public images from the repository, starts PostgreSQL, keeps backups in a named Docker volume, and exposes:

- Main Judgenburn app: `HOST_PORT`, default `7080`
- Public display service: `PUBLIC_PORT`, default `7081`

When `public` is in the same stack, leave `PUBLIC_UPSTREAM_URL=http://web:8080`. If you deploy the public display as a separate cloud container, set `PUBLIC_UPSTREAM_URL` to the reachable main Judgenburn URL, such as a Cloudflare tunnel URL.

Owner accounts can also save the public display URL, heading, and logo URL from Admin Dashboard -> Owner -> Public Display. A logo can be a local static path such as `/static/kairix-judging-system-logo.png` or a full `https://...` URL.

## Share To Another Device

On the same network, use the host computer's LAN IP instead of `localhost`.

Example:

```text
http://192.168.1.50:7080/public
http://192.168.1.50:7080/judge
```

For temporary internet testing, start the optional Cloudflare tunnel:

```bash
docker compose --profile tunnel up -d tunnel
docker compose logs tunnel
```

Look for the `https://...trycloudflare.com` URL. The tunnel is opt-in so a normal local event setup does not expose the service publicly by accident.

## Configuration

Before event day, edit `.env`:

```text
HOST_PORT=7080
POSTGRES_PASSWORD=change_me_before_event_day
```

Keep `.env`, backups, database volumes, and uploaded media out of git. The included `.gitignore` and `.dockerignore` already exclude those local files.

## Install On A New Device

Clone the shared GitHub repository, enter the project folder, then start it.

```bash
git clone https://github.com/Dubcodes/Kairix-Judgenburn.git
cd Kairix-Judgenburn
sh ./run.sh
```

On Windows:

```powershell
git clone https://github.com/Dubcodes/Kairix-Judgenburn.git
cd Kairix-Judgenburn
.\run.ps1
```

The run scripts create `.env` from `.env.example` if it does not exist.

## Seed PINs

- Judge 1: `101`
- Judge 2: `102`
- Graphics: `0201`
- Admin: `1234`
- High Admin: `12345`
- Owner: `123456`

## Demo Import CSV

A 64-car demo import file is included at `demo/demo_competitors_64.csv`. It uses the standard import columns and includes mixed classes, run types, notes, sponsors, engines, plates, and heat numbers so people can quickly demo queueing, public displays, and scoring without typing a whole event by hand.

## Public Data Model

Public pages use `/api/public/snapshot`, a cached read-only snapshot that strips internal IDs, judge data, device data, plates, engine details, sponsor fields, admin graphics config, and score breakdowns. Public score totals are only included when the owner/high-admin setting allows them.

Internal admin, judging, scoring, and OBS pages still use the richer live event state where they need it.

The optional `public` container does not connect to PostgreSQL or expose admin/judge routes. It serves the public display files and proxies only `/api/public/snapshot` from `PUBLIC_UPSTREAM_URL`.

## Scoring Modes

Owner accounts can choose the event scoring system in Admin Dashboard -> Settings.

- Heat count: all heats, or best N heats. Best N is not limited to three heats; if you run five heats and choose Best 3, only the competitor's best three heat totals count.
- Judge aggregation: add all judge totals, average judge totals, median judge total, drop highest/lowest and average the rest, or normalize each heat to 100.
- Example: Heat 1 = 160, Heat 2 = 145, Heat 3 = 90. Best 2 heats gives 305. All heats gives 395.

## Version

The running app version is shown in Admin Dashboard -> Settings. Update `app/version.py` when preparing a release so cloned devices and event laptops can confirm they are on the same build.

## Event-Day Controls

- **Set Next Competitor** moves a competitor directly behind the current run without changing who judges are scoring.
- **Event Scoring System** in Settings controls whether all heats count or only the best N heats, and how judge totals combine.
- Drag competitors in the Competitors page and use **Save Order** to update the queue.
- Delay buttons on Run Control light up when their matching delay is active.
- Owner accounts can edit the quick delay presets in Settings.
- Owner accounts can void/delete a judge score from the scoring monitor with a required reason. The row is kept for audit, marked voided, and removed from live results.
- If a judge has already submitted for the same competitor in the same heat, the judge page treats it as already submitted successfully instead of creating a duplicate score.

## Operating Notes

- PostgreSQL is only exposed inside Docker by default.
- Public pages poll a small cached snapshot instead of opening the full live event stream.
- Judge scoring continues to save drafts locally before syncing, so device/network interruptions have a recovery path.
- Automatic backups are written inside the container to `/app/backups`, mounted to `./backups`.

## Maintenance

Useful commands:

```bash
docker compose ps
docker compose logs -f web
docker compose restart web
docker compose down
```

To update a cloned install:

```bash
git pull
docker compose up -d --build
```
