"""
RouterOS model.
"""
import logging
import time
from typing import List

from models.model import Model
from netcommandlib import parsers
from netcommandlib.connection import Connection, CommandError
from netcommandlib.parsers import get_vertical_data_row
from netcommandlib.image import GenericImage, LocalImage

logger = logging.getLogger("RouterOS")


class RouterOS(Model):
    def __init__(self, connection: Connection):
        self.connection = connection

    def get_platform(self):
        stdout = self.connection.command("/system resource print")
        return get_vertical_data_row(stdout, 'architecture-name')

    def get_software_version(self):
        stdout = self.connection.command("/system resource print")
        return get_vertical_data_row(stdout, 'version').split(None, 1)[0].strip()

    def get_firmware_version(self):
        try:
            stdout = self.connection.command("/system routerboard print")
            return get_vertical_data_row(stdout, 'current-firmware')
        except CommandError:
            # Non routerboard device
            return self.get_software_version()

    def get_supported_image_provider_types(self):
        return ["local"]

    def save_config(self):
        """NOP configuration save"""
        return

    def execute(self, command):
        return self.connection.command(command)

    def get_extra_packages(self):
        data = self.connection.command("/system/package print")
        packages = parsers.get_tabular_data(data, header=["#", "NAME", "VERSION"], skip_after_header=0)
        return [x for x in packages if x["NAME"] != "routeros"]

    def upgrade(self, image: GenericImage, extra_images: List[GenericImage]):
        # TODO: Check for extra packages!
        # Upload image
        if not isinstance(image, LocalImage):
            raise NotImplemented(f"Image type {type(image)} not implemented")

        for extra_image in extra_images:
            if not isinstance(extra_image, LocalImage):
                raise NotImplemented(f"Image type {type(extra_image)} not implemented")
            with open(extra_image.path, 'rb') as f:
                self.connection.upload_file(f, extra_image.filename)

        with open(image.path, 'rb') as f:
            self.connection.upload_file(f, image.filename)

        # Restart device
        try:
            self.connection.run("/system/reboot")
        except TimeoutError:
            pass
        except Exception:
            # TODO Handle only pipe timeouts
            pass
        # Close connection, wait 5 seconds (for device to reboot) and reconnect.
        self.connection.expect_disconnect()
        # Upgrade firmware
        return self.upgrade_firmware()

    def upgrade_firmware(self):
        try:
            stdout = self.connection.command("/system routerboard print")
            current_firmware = get_vertical_data_row(stdout, 'current-firmware')
            upgrade_firmware = get_vertical_data_row(stdout, 'upgrade-firmware')
        except CommandError:
            return True

        if current_firmware != upgrade_firmware:
            self.connection.run("/system routerboard upgrade")
            time.sleep(5)
            try:
                self.connection.run("/system reboot")
            except TimeoutError:
                pass
            self.connection.expect_disconnect()

            # Check current-firmware is same as upgrade-firmware after upgrade
            stdout = self.connection.command("/system routerboard print")
            current_firmware = get_vertical_data_row(stdout, 'current-firmware')
            upgrade_firmware = get_vertical_data_row(stdout, 'upgrade-firmware')

            return current_firmware == upgrade_firmware

    def get_upgrade_package_name(self, version):
        if version.startswith("6"):
            return f"routeros-{self.get_platform()}-{version}.npk"
        return f"routeros-{version}-{self.get_platform()}.npk"

    def get_extra_package_names(self, version):
        data = []
        for package in self.get_extra_packages():
            data.append(f"{package['NAME']}-{version}-{self.get_platform()}.npk")
        return data
