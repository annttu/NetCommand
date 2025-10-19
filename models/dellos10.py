"""
Dell OS10 model.
"""
import logging
import time
from typing import List

from models.model import Model
from netcommandlib import parsers, expect, commands
from netcommandlib.connection import SSHConnection, CommandError
from netcommandlib.parsers import get_vertical_data_row
from netcommandlib.image import NetworkImage, GenericImage

logger = logging.getLogger("Dell OS10")


class OS10(Model):

    PROMPT = "# "

    def __init__(self, connection: SSHConnection, hostname: str):
        self.connection = connection
        self.hostname = hostname

    def get_platform(self):
        stdout = self.execute("show version", timeout=30)
        # OS type is on first row
        return stdout.strip().splitlines()[0].split()[-1].strip()

    def get_software_version(self):
        stdout = self.execute("show version", timeout=30)
        return get_vertical_data_row(stdout, 'Build Version')

    def get_firmware_version(self):
        # TODO: Get real firmware versions
        return self.get_software_version()

    def get_supported_image_provider_types(self):
        return ["http", "https", "tftp", "scp"]

    def save_config(self, dry_run=False):
        self.execute("write memory", timeout=30, dry_run=dry_run)

    def elevate(self):
        # TODO: implement
        return

    def execute(self, command, dry_run=False, **kwargs):
        commands.log_command(self.hostname, command, dry_run=dry_run)
        return self.connection.run_interactive(command, dry_run=dry_run, **kwargs)

    def upgrade(self, image: GenericImage, extra_images: List[GenericImage], dry_run=False):
        # TODO: Check if there's pending update
        command_timeout = 300
        install_timeout = 3600
        answers = {
            "Proceed to reboot the system?": "y",
        }
        # TODO: Implement better dry run
        if dry_run:
            logger.info(f"{self.hostname}: Upgrading device...")
            return True
        if extra_images:
            raise CommandError("Don't know how to handle extra images")
        if not isinstance(image, NetworkImage):
            raise NotImplementedError("Image type {type(image)} not implemented")
        # Upload image
        stdout = self.execute(f"image download {image.get_url()}", timeout=command_timeout)
        if "Download started" not in stdout:
            raise CommandError("image download failed")
        # show image status
        i = 0
        while True:
            stdout = self.execute("show image status", timeout=command_timeout)
            result = parsers.get_vertical_data_row(stdout, "File Transfer State")
            if result == "transfer-success":
                break
            elif result == "download":
                pass
            else:
                raise CommandError(f"image download failed with status: {result}")
            time.sleep(1)
            i += 1
            if i > install_timeout:
                raise CommandError("image download timeout")
        self.execute(f"image install image://{image.filename}", timeout=command_timeout)
        i = 0
        while True:
            stdout = self.execute("show image status", timeout=command_timeout)
            result = parsers.get_vertical_data_row(stdout, "Installation State")
            if result == "idle":
                break
            elif result == "install-success":
                break
            elif result == "install":
                pass
            else:
                raise CommandError(f"image install failed with status: {result}")
            time.sleep(1)
            i += 1
            if i > install_timeout:
                raise CommandError("image install timeout")
        # Wait for image installation
        self.execute("boot system standby")
        raise NotImplementedError("Image installation check not implemented")
        # Restart device
        try:
            self.execute("reload", row_callback=expect.expect_strings(answers), timeout=30)
        except TimeoutError:
            pass
        # Close connection, wait 60 seconds (for device to reboot) and reconnect.
        time.sleep(60)
        self.connection.expect_disconnect()

    def get_upgrade_package_name(self, version):
        return f"OS10-{self.get_platform()}-{version}.bin"
