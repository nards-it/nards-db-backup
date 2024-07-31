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
- Uses dumb-init to handle PID 1 issues and signal forwarding.

## Requirements

- Docker (optional, for containerized deployment)
- Python 3.9
- MySQL or PostGIS database

## Installation

### Using Docker

1. Build the Docker image:
   
   `docker build -t flask_backup_app .`

2. Run the Docker container:

   `docker run -p 5000:5000 --env-file .env flask_backup_app`

### Without Docker

1. Install the required Python packages:

   `pip install -r requirements.txt`

2. Run the application:

   `python app.py`

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
- `[{"cron": "0 0 * * *", "retention_max": 90, "name": "default"}]`

## Usage

### Health Check

Check the health of the last backup operation:

   `curl http://localhost:5000/health`

### Restore Database

Restore the database from a given configuration name or backup file path:

   `flask restore <name_or_path>`

If a configuration name is provided, the application will log the chosen backup file for restore.

## Roadmap

There are currently no planned activities:
- nothing :)

However, we invite the community to suggest new features and improvements! Send us your ideas and help extend the project roadmap!

## Contributions and Support

This project is open source, and we welcome contributions from the community. If you encounter any issues, please open an issue on GitHub. Feel free to contribute new features or improvements.

## License

This project is licensed under the GPL v3. See the [LICENSE](LICENSE) file for details.
