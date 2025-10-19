"""
DELL N-series (OS6) switch model.
"""
import logging
import time
from typing import List

from models.model import Model
from netcommandlib.connection import CommandError, SSHConnection, Actions
from netcommandlib import parsers, commands
from netcommandlib.image import NetworkImage, GenericImage
from netcommandlib.version import compare_version
from netcommandlib import expect


logger = logging.getLogger("Dell N-series")

errors = [
    "% Invalid input detected at",
]


def find_errors(data):
    for row in data:
        for error in errors:
            if error in row:
                return row
    return None


def raise_on_errors(data):
    error = find_errors(data)
    if error:
        raise CommandError(error)


class DellN(Model):
    VERSION_HEADER = ["unit", "active", "backup", "current-active", "next-active"]

    def __init__(self, connection: SSHConnection, hostname: str, enable_password=None):
        self.connection = connection
        self.hostname = hostname
        self.enable_password = enable_password

    def get_platform(self):
        stdout = self.execute("show version", timeout=30)
        model_id = parsers.get_regex_data_row(stdout, r"^System Model ID\.+ (.+)$")
        if model_id.startswith("N"):
            # for example N1548P -> N1500
            return model_id[0:3] + "00"
        return model_id

    def _get_software_versions(self):
        stdout = self.execute("show version", timeout=30)
        versions = parsers.get_tabular_data(stdout, header=self.VERSION_HEADER)
        return versions

    def _get_software_version(self, image):
        stdout = self.execute("show version", timeout=30)
        versions = parsers.get_tabular_data(stdout, header=self.VERSION_HEADER)
        return versions[0][image]

    def get_software_version(self):
        versions = self._get_software_versions()
        return versions[0]["active"]

    def get_firmware_version(self):
        stdout = self.execute("show version", timeout=30)
        return parsers.get_regex_data_row(stdout, r"^CPLD Version\.+ (.+)$")

    def get_supported_image_provider_types(self):
        return ["tftp", "scp"]

    def save_config(self, dry_run=False):
        answers = {
            "Are you sure you want to save?": "y",
        }
        self.elevate()
        stdout = self.execute(
            "copy running-config startup-config",
            timeout=30,
            row_callback=expect.expect_strings(answers),
            dry_run=dry_run
        )
        raise_on_errors(
            stdout
        )
        if "Configuration Saved!" not in stdout:
            raise CommandError("Configuration save didn't succeed")

    def execute(self, command, dry_run=False, **kwargs):
        commands.log_command(self.hostname, command, dry_run=dry_run)
        return self.connection.run_interactive(command, dry_run=dry_run, **kwargs)

    def elevate(self):
        if self.enable_password:
            password = self.enable_password
        else:
            password = Actions.BREAK
        answers = {
            "Password:": password,
        }
        self.connection._wait_prompt()
        self.connection.set_prompt("#")
        raise_on_errors(self.execute("enable", row_callback=expect.expect_strings(answers)))

    def upgrade(self, image: GenericImage, extra_images: List[GenericImage], dry_run: bool = False):
        if extra_images:
            raise CommandError("Don't know how to handle extra images")
        if not isinstance(image, NetworkImage):
            raise NotImplementedError(f"Image type {type(image)} not implemented")
        answers = {
            "Are you sure you want to start?": "y",  # copy
            "Are you sure you want to continue?": "y",  # reload
            "Are you sure you want to reload the stack?": "y",  # reload
            "Remote Password:": image.password,
        }
        self.elevate()
        # Check backup image version
        dry_run_str = ""
        if dry_run:
            dry_run_str = " (DRY RUN)"
        version = self._get_software_version("backup")
        logger.info(f"{self.hostname}: Current version {version}, image version {image.version} {dry_run_str}")

        if compare_version(version, image.version) != 0:
            logger.info(f"{self.hostname}: Upgrading from {version} to {image.version} {dry_run_str}")
            # Upload image
            stdout = self.execute(
                f"copy {image.get_url(credentials=False, skip_port=True)} backup",
                timeout=300,
                row_callback=expect.expect_strings(answers),
                dry_run=dry_run
            )
            if not dry_run:
                raise_on_errors(stdout)
                if not parsers.match_text(stdout, "File transfer operation completed successfully."):
                    raise CommandError(f"Image upload failed: {stdout}")
                # Wait for image installation
                version = self._get_software_version("backup")
                if compare_version(version, image.version) != 0:
                    raise CommandError(f"backup image version {version} didn't match expected {image.version}")
        else:
            logger.info(f"{self.hostname}: Backup image already at expected version")

        version = self._get_software_version("next-active")
        if compare_version(version, image.version) != 0:
            raise_on_errors(self.execute("boot system backup", dry_run=dry_run))
            version = self._get_software_version("next-active")
        if compare_version(version, image.version) != 0 and not dry_run:
            raise CommandError(f"boot image version {version} didn't match expected {image.version}")

        # Restart device
        try:
            raise_on_errors(self.execute(
                "reload",
                row_callback=expect.expect_strings(answers),
                timeout=30,
                dry_run=dry_run
            ))
        except TimeoutError:
            pass

        if dry_run:
            return True

        # Close connection, wait 60 seconds (for device to reboot) and reconnect.
        time.sleep(60)
        self.connection.expect_disconnect()

        return True

    def upgrade_firmware(self, dry_run=False):
        answers = {
            "Are you sure you want to continue?": "y",  # reload
            "Are you sure you want to reload the stack?": "y",  # reload
        }
        # Update bootcode
        self.execute("update bootcode", dry_run=dry_run)
        self.execute("reload", row_callback=expect.expect_strings(answers), dry_run=dry_run)
        if not dry_run:
            self.connection.expect_disconnect()

    def get_upgrade_package_name(self, version):
        return f"{self.get_platform()}v{version}.stk"
