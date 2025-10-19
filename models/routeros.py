"""
RouterOS model.
"""
import logging
import time
from typing import List

from models.model import Model
from netcommandlib import parsers, commands
from netcommandlib.connection import Connection, CommandError
from netcommandlib.parsers import get_vertical_data_row
from netcommandlib.image import GenericImage, LocalImage, HTTPImage
from netcommandlib.version import compare_version

logger = logging.getLogger("RouterOS")


cli_errors = [
    'expected end of command (',
    'bad command name',
    'input does not match any value of',
    'syntax error (',
    'expected command name',
    'invalid internal item number',
    'failure: ',
    'max line length 65535 exceeded!',
    'expected closing',
    'no such item',
    'value of passphrase should not be shorter than',
    'invalid value ',
]

cli_duplicate_warnings = [
    'failure: already have',
]

cli_warnings = []


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
        "wireless",
        "wifi-qcom",
        "wifi-qcom-ac",
    ]

    def __init__(self, connection: Connection, hostname: str):
        self.connection = connection
        self.hostname = hostname

    def get_username(self, username):
        return f"{username}+ct511w4098h"

    def get_platform(self):
        stdout = self.execute("/system resource print")
        return get_vertical_data_row(stdout, 'architecture-name')

    def get_software_version(self):
        stdout = self.execute("/system resource print")
        return get_vertical_data_row(stdout, 'version').split(None, 1)[0].strip()

    def get_firmware_version(self):
        try:
            stdout = self.execute("/system routerboard print")
            return get_vertical_data_row(stdout, 'current-firmware')
        except CommandError:
            # Non routerboard device
            return self.get_software_version()

    def get_firmware_type(self):
        try:
            stdout = self.execute("/system routerboard print")
            return get_vertical_data_row(stdout, 'firmware-type')
        except CommandError:
            return None

    def get_supported_image_provider_types(self):
        return ["local"]

    def save_config(self, dry_run=False):
        """NOP configuration save"""
        return

    def execute(self, command, dry_run=False, **kwargs):
        commands.log_command(self.hostname, command, dry_run=dry_run)
        return self.command(command, dry_run=dry_run, **kwargs)

    def command(self, command, ignore_errors=False, ignore_warnings=False, ignore_duplicate=False, dry_run=False):
        if dry_run:
            return "DRY RUN"
        (stdout, stderr) = self.connection.run(command)

        if not ignore_errors:
            if stderr:
                raise CommandError("SSH returned error: %s" % (stderr,))
            for exception in cli_errors:
                if exception in stdout:
                    raise CommandError("SSH returned error: %s" % (stdout,))
            if not ignore_warnings or not ignore_duplicate:
                for warning in cli_warnings:
                    if warning in stdout:
                        raise CommandError("SSH returned warning: %s" % (stdout,))
            if not ignore_duplicate:
                for warning in cli_duplicate_warnings:
                    if warning in stdout:
                        raise CommandError("SSH returned duplication warning: %s" % (stdout,))
        if 'input does not match ' in stdout:
            raise CommandError("SSH returned error %s" % (stdout,))
        logger.debug("%s: SSH:\n%s", self.hostname, stdout)
        return stdout

    def execute_block(self, commands, dry_run=False, **kwargs):
        out = ""
        buffer = ""
        for command in commands:
            command = command.strip()
            if not command or command.startswith("#"):
                continue
            if command.startswith("/") and buffer:
                # execute buffer
                out += self.execute("{ " + buffer + ' }', dry_run=dry_run)
                buffer = ""
            buffer += command + "; "
        if buffer:
            out += self.execute("{ " + buffer + ' }', dry_run=dry_run)
        return out

    def download_image(self, image: HTTPImage, dry_run):
        return self.execute(f"/tool fetch url=\"{image.get_url()}\" output=file", dry_run=dry_run)

    def get_extra_packages(self, version):
        """
        TODO: Wifiwave2 package has been replaced in 7.13 with wifi-qcom and wifi-qcom-ac packages.
        TODO: Devices with wlan interface need wireless package starting from version 7.13
        """
        current_version = self.get_software_version()
        firmware_type = self.get_firmware_type()
        data = self.command("/system package print")
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
        extra_packages = [x for x in packages if x["NAME"] in self.extra_packages]
        if firmware_type:
            if compare_version(current_version, "7.13") < 0 and compare_version(version, "7.13") >= 0:
                idx = 0
                for package in extra_packages:
                    if package["NAME"] == "wifiwave2":
                        del extra_packages[idx]
                        if firmware_type.startswith("ipq40"):
                            extra_packages.append({"NAME": "wifi-qcom-ac", "VERSION": current_version})
                        elif firmware_type.startswith("ipq60"):
                            extra_packages.append({"NAME": "wifi-qcom", "VERSION": current_version})
                        else:
                            logger.warning(
                                f"{self.hostname}: Don't know replacement for wifiwave2 package for {firmware_type}"
                            )
                            raise NotImplementedError(
                                f"Don't know replacement for wifiwave2 package for {firmware_type}"
                            )
                        break
                    idx += 1
                else:
                    # We need a wireless package if we have wlan interfaces
                    interface_raw_data = self.command("/interface print detail")
                    if 'type="wlan"' in interface_raw_data:
                        extra_packages.append({"NAME": "wireless", "VERSION": current_version})
        return extra_packages

    def upgrade(self, image: GenericImage, extra_images: List[GenericImage], dry_run=False):
        # TODO: Check for extra packages!
        # Upload image
        if not isinstance(image, LocalImage) and not isinstance(image, HTTPImage):
            raise NotImplementedError(f"Image type {type(image)} not implemented")

        for extra_image in extra_images:
            if isinstance(extra_image, LocalImage):
                logger.info(
                    f"{self.hostname}: Uploading new image file '{extra_image.filename}' "
                    f"to {self.connection.get_address()}"
                )
                if not dry_run:
                    with open(extra_image.path, 'rb') as f:
                        self.connection.upload_file(f, extra_image.filename)
            elif isinstance(extra_image, HTTPImage):
                self.download_image(image=extra_image, dry_run=dry_run)
            else:
                raise NotImplementedError(f"Image type {type(extra_image)} not implemented")

        current_version = self.get_software_version()

        if compare_version(current_version, "7.12.0") < 0 and compare_version(image.version, "7.13.0") >= 0:
            # We need to update first to version 7.12.1 or 7.12.0 and continue then to >= 7.13.
            raise RuntimeError("Please update first to version 12.1 and after that to later versions")

        if isinstance(image, LocalImage):
            logger.info(
                f"{self.hostname}: Uploading new image file '{image.filename}' to {self.connection.get_address()}"
            )
            if not dry_run:
                with open(image.path, 'rb') as f:
                    self.connection.upload_file(f, image.filename)
        elif isinstance(image, HTTPImage):
            logger.info(
                f"{self.hostname}: Downloading new image file '{image.get_url()}' to {self.connection.get_address()}"
            )
            self.download_image(image=image, dry_run=dry_run)

        # Restart device
        logger.info(f"{self.hostname}: Rebooting {self.connection.get_address()}")
        try:
            self.execute("/system reboot", dry_run=dry_run)
        except TimeoutError:
            pass
        except Exception:
            # TODO Handle only pipe timeouts
            pass

        if not dry_run:
            # Close connection, wait 5 seconds (for device to reboot) and reconnect.
            self.connection.expect_disconnect()
        # Upgrade firmware
        return self.upgrade_firmware(dry_run=dry_run)

    def upgrade_firmware(self, dry_run=False):
        try:
            stdout = self.execute("/system routerboard print")
            current_firmware = get_vertical_data_row(stdout, 'current-firmware')
            upgrade_firmware = get_vertical_data_row(stdout, 'upgrade-firmware')
        except CommandError:
            logger.exception(f"{self.hostname}: Failed to check firmware version")
            return True

        if current_firmware != upgrade_firmware:
            logger.info(f"{self.hostname}: Upgrading routerboard firmware on {self.connection.get_address()}")
            self.execute("/system routerboard upgrade", dry_run=dry_run)
            # Wait for "Firmware upgraded successfully, please reboot for changes to take effect!" text
            if not dry_run:
                for i in range(5):
                    time.sleep(5)
                    stdout = self.command("/system routerboard print")
                    if 'please reboot' in stdout:
                        break
                else:
                    raise RuntimeError("Timeout while waiting firmware upgrade")

            logger.info(f"{self.hostname}: Rebooting {self.connection.get_address()}")
            try:
                self.execute("/system reboot", dry_run=dry_run)
            except TimeoutError:
                pass

            if dry_run:
                return True

            self.connection.expect_disconnect()

            # Check current-firmware is same as upgrade-firmware after upgrade
            stdout = self.command("/system routerboard print")
            current_firmware = get_vertical_data_row(stdout, 'current-firmware')
            upgrade_firmware = get_vertical_data_row(stdout, 'upgrade-firmware')

        if dry_run:
            return True

        return current_firmware == upgrade_firmware

    def get_upgrade_package_name(self, version):
        if version.startswith("6"):
            return f"routeros-{self.get_platform()}-{version}.npk"
        return f"routeros-{version}-{self.get_platform()}.npk"

    def get_extra_package_names(self, version):
        """
        :param version: New version
        :return: list of extra packages
        """
        data = []
        for package in self.get_extra_packages(version):
            data.append(f"{package['NAME']}-{version}-{self.get_platform()}.npk")
        return data
