import logging

logger = logging.getLogger("commands")


def log_command(host, command, dry_run=False):
    dry_run_string = " (DRY RUN)" if dry_run else ""
    logger.debug("%s: Executing command%s: %s", host, dry_run_string, command)
