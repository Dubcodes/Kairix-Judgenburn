# Kairix Judgenburn System

Live-event judging, run control, scoring, queue display, public results, and OBS graphics for burnout competitions.

## Quick Start

Clone the project onto the event computer, then run one command from the project folder.

Windows PowerShell:

```powershell
.\run.ps1
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

## Git Setup

This folder is ready to become a git repository:

```bash
git init
git add .
git commit -m "Initial Kairix Judgenburn system"
```

After it is pushed to GitHub or another git host, a new device can use:

```bash
git clone https://github.com/Dubcodes/Kairix-Judgenburn.git
cd Kairix-Judgenburn
cp .env.example .env
sh ./run.sh
```

On Windows, use `.\run.ps1` instead of `sh ./run.sh`.

## Seed PINs

- Judge 1: `101`
- Judge 2: `102`
- Graphics: `0201`
- Admin: `1234`
- High Admin: `12345`
- Owner: `123456`

## Public Data Model

Public pages use `/api/public/snapshot`, a cached read-only snapshot that strips internal IDs, judge data, device data, plates, engine details, sponsor fields, admin graphics config, and score breakdowns. Public score totals are only included when the owner/high-admin setting allows them.

Internal admin, judging, scoring, and OBS pages still use the richer live event state where they need it.

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
