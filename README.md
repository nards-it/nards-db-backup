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

A Flask application that schedules and manages database backups using cron jobs. It supports both MySQL and PostGIS databases and can restore backups via command-line arguments.

## Features

- Schedule database backups using cron expressions.
- Retain a specified number of backups.
- Restore database from the most recent backup.
- Health check endpoint to monitor the status of the last backup operation.
- Configurable via environment variables.

## Configuration

Configure the application via environment variables. Create a `.env` file with the following variables:

- `DB_HOST=localhost`
- `DB_PORT=5432`
- `DB_USER=user`
- `DB_PASSWORD=password`
- `DB_TYPE=mysql` or `postgis`
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
      DB_PORT: '5432' # postgres/postgis: 5432; mysql: 3306
      DB_USER: 'user'
      DB_PASSWORD: 'password'
      DB_TYPE: 'postgres' # postgres/postgis/mysql
      BACKUP_DIR: /backups
      CRON_CONFIGS: '[{"cron": "0 * * * *", "retention_max": 15, "name": "every"},{"cron": "0 * * * *", "retention_max": 1, "name": "hourly"}]'
      RESTORE_CONFIG_NAME: 'hourly'
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
- Python 3.9
- MySQL or PostGIS database

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

## License

This project is licensed under the GPL v3. See the [LICENSE](LICENSE) file for details.
