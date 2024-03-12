"""
Cisco IOS switch model.
"""
import logging
import time
from typing import List, Union

from models.model import Model
from netcommandlib.connection import CommandError, SSHConnection, TelnetConnection, Actions
from netcommandlib import parsers, commands
from netcommandlib.image import NetworkImage, GenericImage
from netcommandlib import expect


logger = logging.getLogger("Cisco IOS")

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


class IOS(Model):
    VERSION_HEADER = ["Switch", "Ports", "Model", "SW Version", "SW Image", "Mode"]
    VERSION_HEADER_XE = ["Switch", "Ports", "Model", "SW Version", "SW Image"]

    def __init__(self, connection: Union[SSHConnection, TelnetConnection], hostname: str, enable_password=None):
        self.connection = connection
        self.hostname = hostname
        self.enable_password = enable_password
        self.connection.connect()
        self.connection.run_interactive("terminal length 0")

    def get_platform(self):
        stdout = self.execute("show version", timeout=30)
        model_id = parsers.get_regex_data_row(stdout, r"^Model Number\.+: (.+)$")
        if model_id.startswith("N"):
            # for example N1548P -> N1500
            return model_id[0:3] + "00"
        return model_id

    def _get_software_versions(self):
        stdout = self.execute("show version", timeout=30)
        versions = parsers.get_tabular_data_fixed_header_width(stdout, header=self.VERSION_HEADER)
        logger.debug("Versions: %s", (versions,))
        return versions

    @staticmethod
    def login_dialog(username, password):
        def wrapped(row):
            if row.endswith("Username:"):
                return username + "\n"
            elif row.endswith("Password:"):
                return password + "\n"
            elif row.startswith("% Authentication failed"):
                return Actions.BREAK
            return None
        return wrapped

    def get_software_version(self):
        versions = self._get_software_versions()
        return versions[0]["SW Version"]

    def get_firmware_version(self):
        # TODO: what is correct version for this?
        return self.get_software_version()

    def get_supported_image_provider_types(self):
        return ["tftp", "scp", "http", "https"]

    def save_config(self, dry_run=False):
        self.elevate()
        stdout = self.execute("write memory", timeout=30, dry_run=dry_run)
        if dry_run:
            return
        if "[OK]" not in stdout:
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
        raise_on_errors(self.connection.run_interactive(f"enable", row_callback=expect.expect_strings(answers)))

    def upgrade(self, image: GenericImage, extra_images: List[GenericImage], dry_run=False):
        raise NotImplemented("This function is not implemented properly")

    def upgrade_firmware(self):
        raise NotImplemented("Not implemented")

    def get_upgrade_package_name(self, version):
        raise NotImplemented("Not implemented")
