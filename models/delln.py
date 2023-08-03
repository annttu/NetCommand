"""
DELL N-series switch model.
"""
import logging
import time
from typing import List

from models.model import Model
from netcommandlib.connection import CommandError, SSHConnection, Actions
from netcommandlib import parsers
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

    def __init__(self, connection: SSHConnection, enable_password=None):
        self.connection = connection
        self.enable_password = enable_password

    def get_platform(self):
        stdout = self.connection.run_interactive("show version", timeout=30)
        model_id = parsers.get_regex_data_row(stdout, r"^System Model ID\.+ (.+)$")
        if model_id.startswith("N"):
            # for example N1548P -> N1500
            return model_id[0:3] + "00"
        return model_id

    def _get_software_versions(self):
        stdout = self.connection.run_interactive("show version", timeout=30)
        versions = parsers.get_tabular_data(stdout, header=self.VERSION_HEADER)
        return versions

    def _get_software_version(self, image):
        stdout = self.connection.run_interactive("show version", timeout=30)
        versions = parsers.get_tabular_data(stdout, header=self.VERSION_HEADER)
        return versions[0][image]

    def get_software_version(self):
        versions = self._get_software_versions()
        return versions[0]["active"]

    def get_firmware_version(self):
        stdout = self.connection.run_interactive("show version", timeout=30)
        return parsers.get_regex_data_row(stdout, r"^CPLD Version\.+ (.+)$")

    def get_supported_image_provider_types(self):
        return ["tftp", "scp"]

    def save_config(self):
        answers = {
            "Are you sure you want to save?": "y",
        }
        self.elevate()
        stdout = self.connection.run_interactive("copy running-config startup-config", timeout=30,
                                                row_callback=expect.expect_strings(answers))
        raise_on_errors(
            stdout
        )
        if "Configuration Saved!" not in stdout:
            raise CommandError("Configuration save didn't succeed")

    def execute(self, command):
        return self.connection.run_interactive(command)

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
        raise_on_errors(self.connection.run_interactive(f"enable", row_callback=expect.expect_strings(answers)))

    def upgrade(self, image: GenericImage, extra_images: List[GenericImage]):
        if extra_images:
            raise CommandError("Don't know how to handle extra images")
        if not isinstance(image, NetworkImage):
            raise NotImplemented(f"Image type {type(image)} not implemented")
        answers = {
            "Are you sure you want to start?": "y",  # copy
            "Are you sure you want to continue?": "y",  # reload
            "Are you sure you want to reload the stack?": "y",  # reload
            "Remote Password:": image.password,
        }
        self.elevate()
        # Check backup image version
        version = self._get_software_version("backup")
        if compare_version(version, image.version) != 0:
            # Upload image
            stdout = self.connection.run_interactive(f"copy {image.get_url(credentials=False, skip_port=True)} backup",
                                                     timeout=300, row_callback=expect.expect_strings(answers))
            raise_on_errors(stdout)
            if not parsers.match_text(stdout, "File transfer operation completed successfully."):
                raise CommandError(f"Image upload failed: {stdout}")
            # Wait for image installation
            version = self._get_software_version("backup")
            if compare_version(version, image.version) != 0:
                raise CommandError(f"backup image version {version} didn't match expected {image.version}")
        else:
            logger.info("Backup image already at expected version")

        version = self._get_software_version("next-active")
        if compare_version(version, image.version) != 0:
            raise_on_errors(self.connection.run_interactive("boot system backup"))
            version = self._get_software_version("next-active")
        if compare_version(version, image.version) != 0:
            raise CommandError(f"boot image version {version} didn't match expected {image.version}")

        # raise NotImplemented
        # Restart device
        try:
            raise_on_errors(self.connection.run_interactive("reload", row_callback=expect.expect_strings(answers),
                                                            timeout=30))
        except TimeoutError:
            pass
        # Close connection, wait 60 seconds (for device to reboot) and reconnect.
        time.sleep(60)
        self.connection.expect_disconnect()

        return True

    def upgrade_firmware(self):
        answers = {
            "Are you sure you want to continue?": "y",  # reload
            "Are you sure you want to reload the stack?": "y",  # reload
        }
        # Update bootcode
        self.connection.run_interactive(f"update bootcode")
        self.connection.run_interactive(f"reload", row_callback=expect.expect_strings(answers))
        self.connection.expect_disconnect()

    def get_upgrade_package_name(self, version):
        return f"{self.get_platform()}v{version}.stk"
