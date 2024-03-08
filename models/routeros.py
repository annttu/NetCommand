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
from netcommandlib.version import compare_version

logger = logging.getLogger("RouterOS")


class RouterOS(Model):
    extra_packages = [
        "calea",
        "container",
        "dude",
        "gps",
        "iot",
        "lora",
        "rose-storage",
        "tr069-client",
        "ups",
        "user-manager",
        "wifiwave2",
        "zerotier",
    ]

    def __init__(self, connection: Connection):
        self.connection = connection

    def get_username(self, username):
        return f"{username}+ct511w4098h"

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

    def execute_block(self, commands):
        out = ""
        buffer = ""
        for command in commands:
            command = command.strip()
            if not command or command.startswith("#"):
                continue
            if command.startswith("/") and buffer:
                # execute buffer
                out += (self.execute("{ " + buffer + ' }'))
                buffer = ""
            buffer += command + "; "
        if buffer:
            out += (self.execute("{ " + buffer + ' }'))
        return out

    def get_extra_packages(self):
        data = self.connection.command("/system package print")
        packages = parsers.get_tabular_data(
            data,
            header=["#", "NAME", "VERSION", "BUILD-TIME", "SIZE"],
            skip_after_header=0
        )
        if not packages:
            # Maybe routeros 7.0-7.12
            packages = parsers.get_tabular_data(
                data,
                header=["#", "NAME", "VERSION"],
                skip_after_header=0
            )
        if not packages:
            # Maybe routeros 6
            packages = parsers.get_tabular_data(
                data,
                header=["#", "NAME", "VERSION", "SCHEDULED"],
                skip_after_header=0
            )
        if not packages:
            raise RuntimeError("Failed to get installed packages")
        return [x for x in packages if x["NAME"] in self.extra_packages]

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

        current_version = self.get_software_version()

        if compare_version(current_version, "7.12.0") < 0 and compare_version(image.version, "7.13.0") >= 0:
            # We need to update first to version 7.12.1 or 7.12.0 and continue then to >= 7.13.
            raise RuntimeError("Please update first to version 12.1 and after that to later versions")

        logger.info(f"Uploading new image file '{image.filename}' to {self.connection.get_address()}")
        with open(image.path, 'rb') as f:
            self.connection.upload_file(f, image.filename)

        # Restart device
        logger.info(f"Rebooting {self.connection.get_address()}")
        try:
            self.connection.run("/system reboot")
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
            logger.exception("Failed to check firmware version")
            return True

        if current_firmware != upgrade_firmware:
            logger.info(f"Upgrading routerboard firmware on {self.connection.get_address()}")
            self.connection.run("/system routerboard upgrade")
            # Wait for "Firmware upgraded successfully, please reboot for changes to take effect!" text
            for i in range(5):
                time.sleep(5)
                stdout = self.connection.command("/system routerboard print")
                if 'please reboot' in stdout:
                    break
            else:
                raise RuntimeError("Timeout while waiting firmware upgrade")

            logger.info(f"Rebooting {self.connection.get_address()}")
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
