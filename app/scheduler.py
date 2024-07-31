from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from pathlib import Path
import os
import logging


class Scheduler:
    """
    Scheduler class to manage cron-based backup tasks.

    Attributes:
        db_module (AbstractModule): The database module to interact with the database.
        cron_configs (list): List of cron configurations.
        backup_dir (Path): The root directory for storing backups.
        health (bool): Global health state of the last backup operation.
    """

    def __init__(self, db_module, cron_configs, backup_dir):
        """
        Initialize the Scheduler with database module, cron configs, and backup directory.

        Args:
            db_module (AbstractModule): The database module.
            cron_configs (list): List of cron configuration dictionaries.
            backup_dir (Path): The root directory for backups.
        """
        self.scheduler = BackgroundScheduler()
        self.db_module = db_module
        self.cron_configs = cron_configs
        self.backup_dir = backup_dir
        self.health = True
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Start the scheduler and add jobs based on cron configurations."""
        for cron_config in self.cron_configs:
            cron_expr = cron_config["cron"]
            retention_max = cron_config.get("retention_max")
            cron_name = cron_config.get("name")
            self.logger.info(f"Scheduling backup for cron configuration: {cron_name}")
            trigger = CronTrigger.from_crontab(cron_expr)
            self.scheduler.add_job(self.run_backup, trigger, args=[cron_name, retention_max])
        self.scheduler.start()

    def run_backup(self, cron_name, retention_max):
        """
        Execute the backup job for a specific cron configuration.

        Args:
            cron_name (str): The name of the cron configuration.
            retention_max (int): The maximum number of backups to retain.
        """
        self.logger.info(f"Running backup for cron configuration: {cron_name}")
        try:
            databases = self.db_module.list_all_databases()
            self.logger.info(f"Detected the folliwing databases: {databases}")
            for db in databases:
                backup_file = self.calculate_backup_file_path(cron_name, db)
                success = self.db_module.backup_database(db, backup_file)
                if success:
                    self.cleanup_old_backups(cron_name, db, retention_max)
                self.health = success
        except Exception as e:
            self.logger.error(f"Error during backup: {e}")
            self.health = False

    def calculate_backup_file_path(self, cron_name, db_name):
        """
        Calculate the file path for the backup.

        Args:
            cron_name (str): The name of the cron configuration.
            db_name (str): The name of the database.

        Returns:
            Path: The calculated backup file path.
        """
        now = datetime.now()
        backup_path = self.backup_dir / cron_name / str(now.year) / str(now.month) / str(now.day)
        backup_path.mkdir(parents=True, exist_ok=True)
        backup_file = backup_path / f"{db_name}.{now.strftime('%Y%m%d%H%M%S')}.backup"
        self.logger.info(f"Calculated backup file path: {backup_file}")
        return backup_file

    def cleanup_old_backups(self, cron_name, db_name, retention_max):
        """
        Clean up old backups exceeding the retention limit.

        Args:
            cron_name (str): The name of the cron configuration.
            db_name (str): The name of the database.
            retention_max (int): The maximum number of backups to retain.
        """
        db_backup_dir = self.backup_dir / cron_name
        all_backups = list(db_backup_dir.glob(f'**/{db_name}.*.backup'))
        all_backups.sort(key=os.path.getmtime, reverse=True)
        self.logger.info(f"Cleaning up old backups on '{cron_name}' for '{db_name}' db, keeping the latest {retention_max} backups")
        if len(all_backups) > retention_max:
            for old_backup in all_backups[retention_max:]:
                self.logger.info(f"Deleting old backup: {old_backup}")
                old_backup.unlink()

    def get_health(self):
        """
        Get the current health state of the last backup operation.

        Returns:
            bool: The health state.
        """
        return self.health
