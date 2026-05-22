# Database Migrations

This project now has Alembic wiring so future schema changes can be tracked
instead of being hidden in startup code.

Current state:

- `20260507_0001_baseline` is a baseline revision for the schema the app
  currently creates with SQLAlchemy.
- Existing event databases should be stamped to the baseline once the rebuilt
  image includes Alembic:

```bash
docker compose exec web alembic stamp head
```

For the next real schema change:

```bash
docker compose exec web alembic revision --autogenerate -m "describe change"
docker compose exec web alembic upgrade head
```

The app still runs its compatibility schema checks at startup for now. Those
can be removed after the first few migrations have been tested against a fresh
database and an existing event database.
