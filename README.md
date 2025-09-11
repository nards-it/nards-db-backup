![Docker Image Version (latest semver)](https://img.shields.io/docker/v/nards/nards-db-backup?sort=semver&label=Version&logo=docker)
![Docker Image Size (latest semver)](https://img.shields.io/docker/image-size/nards/nards-db-backup?label=Size&logo=docker)
![Docker Pulls](https://img.shields.io/docker/pulls/nards/nards-db-backup?label=Pulls&logo=docker)
![Docker Stars](https://img.shields.io/docker/stars/nards/nards-db-backup?label=Stars&logo=docker)
![GitHub Repo forks](https://img.shields.io/github/forks/nards-it/nards-db-backup?label=Forks&logo=github)
![GitHub Repo stars](https://img.shields.io/github/stars/nards-it/nards-db-backup?label=Stars&logo=github)

![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/nards-it/nards-db-backup/main.yaml?label=Latest%20build&logo=github)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/nards-it/nards-db-backup/release.yaml?label=Last%20release%20build&logo=github)
![GitHub issues](https://img.shields.io/github/issues/nards-it/nards-db-backup?label=Issues&logo=github)
![GitHub pull requests](https://img.shields.io/github/issues-pr/nards-it/nards-db-backup?label=Pull%20requests&logo=github)
![GitHub commits since latest release (by SemVer)](https://img.shields.io/github/commits-since/nards-it/nards-db-backup/latest?sort=semver)
![GitHub Licence](https://img.shields.io/github/license/nards-it/nards-db-backup)

# Nards DB Backup

Nards DB Backup is a database backup system configurable via Docker. It supports automated backups and the automatic restoration of the last backup on startup (if configured), ensuring that the database is always aligned with the most recent backups. This project is ideal for users who use databases via Docker Compose or Kubernetes and are looking for a solution to automate backups.

# Flask Backup Application

A Flask application that schedules and manages database backups using cron jobs. It supports MySQL, PostgreSQL, MongoDB, PostGIS and GraphDB databases and can restore backups via command-line arguments.
A Flask application that schedules and manages database backups using cron jobs. It supports MySQL, PostGIS, PostgreSQL, MongoDB, Redis , and GraphDB databases and can restore backups via command-line arguments.

## Features

- Schedule database backups using cron expressions.
- Retain a specified number of backups.
- Restore database from the most recent backup.
- Health check endpoint to monitor the status of the last backup operation.
- Configurable via environment variables.
- PostGIS extension-aware backups: detects installed extensions (e.g., PostGIS, pgvector) and generates a pre-restore script to recreate them automatically.

## Configuration

Configure the application via environment variables. Create a `.env` file with the following variables:

- `DB_HOST=localhost`
- `DB_PORT=5432` # (e.g., MySQL: 3306, Postgres/PostGIS: 5432, MongoDB: 27017)
- `DB_USER=user`
- `DB_PASSWORD=password`
- `DB_MAINTENANCE_NAME=mydb` # For MongoDB, this is often 'admin' if using auth # For SQL databases; less relevant for Redis
- `DB_TYPE=mysql`, `postgres`, `postgis`, `postgres`, or `redis` or `postgres` or `mongodb`, or `graphdb`
  - (When `DB_TYPE=graphdb`, `DB_PORT` is typically `7200`. `DB_USER` and `DB_PASSWORD` can often be left empty for default GraphDB Free installations if security is not enabled.)
- `CRON_CONFIGS='[{"cron": "0 0 * * *", "retention_max": 90, "name": "default"}]'`
- `RESTORE_CONFIG_NAME=""`

### CRON_CONFIGS

- If only a cron string is passed, `retention_max` will default to 90 and `name` will default to "default".
- If a JSON object is passed as a string, the passed configuration will be used.
- If the JSON object is missing required fields, the application will log the required format and raise an error.

Example of CRON_CONFIGS:
- `[{"cron": "0 0 * * *", "retention_max": 90, "name": "default"}]`: creates a backup every day a midnight and keep for 90 days
- `[{"cron": "0 * * * *", "retention_max": 24, "name": "hourly"}, {"cron": "0 0 * * *", "retention_max": 24, "name": "monthly"}]`: creates a backup every hour and keep for a day in folder named 'hourly', a backup every 1 of the month and keep for 2 years in folder named 'monthly'

## Usage

### Docker compose

An example of docker compose is provided into docker-compose.yml file. The same example is provided below:

```yaml
services:
  nards_db_backup:
    image: nards/nards-db-backup:latest
    build: .
    environment:
      DB_HOST: 'database'
      DB_PORT: '5432' # postgres/postgis: 5432; mysql: 3306; graphdb: 7200; mongodb: 27017; redis: 6379
      DB_USER: 'user'
      DB_PASSWORD: 'password'
      DB_MAINTENANCE_NAME: 'mydatabase' # For SQL databases; for Redis, typically not used or set to 0 for the default DB., for MongoDB often 'admin'
      DB_TYPE: 'postgres' # postgres/postgis/mysql/mongodb/redis/graphdb
      BACKUP_DIR: /backups
      CRON_CONFIGS: '[{"cron": "0 * * * *", "retention_max": 15, "name": "every"},{"cron": "0 * * * *", "retention_max": 1, "name": "hourly"}]'
      # RESTORE_CONFIG_NAME: 'hourly' # When you have to restore some content
    volumes:
      - ./backups:/backups
```

### Health Check

HealthCheck is automatically included into Docker image and provides an url to verify if backups works correctly:

   `http://localhost:5000/health`

### Restore Database

Restore the database from a given configuration name or backup file path:

   `docker exec <container_name> flask restore <name_or_path>`

If a valid name_or_path is provided it restores this file to the database as configured with environment variables, else it tries to restore the latest backup from the backup configuration name provided with `RESTORE_CONFIG_NAME`. 

If a configuration name is provided, the application will log the chosen backup file for restore.

### PostGIS Extensions (pgvector, etc.)

- When backing up a PostGIS database, the app inspects installed extensions (excluding `plpgsql`) and writes a companion `<backup>.pre.sql` with `CREATE EXTENSION IF NOT EXISTS ...` statements (always including `postgis`, plus any others like `vector`).
- During restore, the app executes `<backup>.pre.sql` before `pg_restore` so that types/functions from extensions are available.
- Ensure the target server has required extension packages installed beforehand (for example on Debian-based Postgres 14: `postgresql-14-pgvector` for pgvector), otherwise `CREATE EXTENSION` will fail.

## Roadmap

There are currently no planned activities:
- actually nothing :)

However, we invite the community to suggest new features and improvements! Send us your ideas and help extend the project roadmap!

## Contributing

You could contribute to project as you like.

You could open issue when you want to propose a feature, a fix, report a bug or anythink else!

When you report a bug I ask you to include into Issue:
1. What is the bug you found
2. When your bug appears
3. How to build a replicable test case

You're welcome to implement features too:
1. Fork it!
2. Create your feature branch: `git checkout -b my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin my-new-feature`
5. Submit a pull request :D

You can also mail me: [giuseppe\@nards.it](mailto:giuseppe@nards.it?subject=[nards-db-backup] Request)

## Development

### Requirements

- Docker (optional, for containerized deployment)
- Python 3.9 (or compatible, e.g., 3.10 as per Dockerfile)
- MySQL, PostgreSQL, PostGIS, PostgreSQL, Redis, MongoDB, or GraphDB database

### Build using Docker

1. Build the Docker image:
   
   `docker build -t flask_backup_app .`

2. Run the Docker container:

   `docker run -p 5000:5000 --env-file .env flask_backup_app`

### Build without Docker

1. Install the required Python packages:

   `pip install -r requirements.txt`

2. Run the application:

   `python app.py`

## Testing

You can run the test suite in two ways, either mirroring the CI pipeline with Docker Compose, or directly from your local virtual environment using pytest (with Docker-managed services).

### CI-like (Docker Compose)

- Run tests in containers (same as GitHub Actions):

  `docker compose -f docker-compose.test.yml down -v && docker compose -f docker-compose.test.yml up --build --exit-code-from test-runner`

- Tear down (optional if you used `--exit-code-from`, containers stop automatically):

  `docker compose -f docker-compose.test.yml down -v`

- Redis note: in the test compose, the `redis` service runs in a tiny restart loop so that the test's `SHUTDOWN` does not terminate the container and abort the Compose run. This applies only to the test compose.
  
- MongoDB note: the service is named `mongodb` in `docker-compose.test.yml`. The `test-runner` exports `DB_HOST_MONGODB=mongodb`, `DB_PORT_MONGODB=27017`, `DB_USER_MONGODB=testuser`, `DB_PASSWORD_MONGODB=testpassword`, `DB_NAME_MONGODB=admin` for the tests.

### Local venv + pytest

- Requirements:
  - Docker installed and running
  - Database CLI tools available on your host PATH:
    - MySQL: `mysqldump` (from `mariadb-client` or `mysql-client`)
    - PostgreSQL: `pg_dump`, `pg_restore`, `psql` (from `postgresql-client`)
  - Python dependencies installed: `pip install -r requirements.txt`

- Run tests from your venv; the test stack is auto-started by pytest (pytest-docker):

  `source venv/bin/activate && pytest -q`

- Notes:
  - `tests/conftest.py` automatically brings up services from `tests/docker-compose.yml` and exports the needed env vars; no manual setup needed.
  - Includes MongoDB via the `mongodb` service; credentials: `testuser` / `testpassword` with `authSource=admin`.
  - If you have an existing container named `mysql` running, you may see a name conflict. Stop it or run:

    `docker compose -f tests/docker-compose.yml down -v`

  - Redis note (local venv): if reading/writing `tests/redis-data/dump.rdb` hits a PermissionError on your host, the RedisModule automatically falls back to copying via `docker cp` by detecting the Redis container. This requires the `docker` CLI to be available locally.


## License

This project is licensed under the GPL v3. See the [LICENSE](LICENSE) file for details.
