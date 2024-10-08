import logging
from abc import abstractmethod, ABCMeta


class Model(object):
    __metaclass__ = ABCMeta

    PROMPT = ">"

    def get_username(self, username):
        return username

    @abstractmethod
    def get_platform(self):
        """
        Returns device platform (cpu arch or device model)
        """
        raise NotImplemented

    @abstractmethod
    def get_software_version(self):
        """
        Returns current software version
        """
        raise NotImplemented

    @abstractmethod
    def get_firmware_version(self):
        """
        Returns current firmware version
        :return:
        """
        raise NotImplemented

    @staticmethod
    def login_dialog(username, password):
        raise NotImplemented

    @abstractmethod
    def save_config(self, dry_run=False):
        """
        Save current configuration to device
        :return:
        """
        raise NotImplemented

    @abstractmethod
    def upgrade(self, image, extra_images, dry_run=False):
        """
        Upgrade device with image
        :param image:
        :return:
        """
        raise NotImplemented

    @abstractmethod
    def execute(self, command, dry_run=False, **kwargs):
        """
        Execute command
        """
        raise NotImplemented

    def execute_block(self, commands, dry_run=False, **kwargs):
        out = []
        for command in commands:
            out.append(self.execute(command, dry_run=dry_run, **kwargs))
        return out

    @abstractmethod
    def get_upgrade_package_name(self, version):
        raise NotImplemented

    def get_extra_package_names(self, version):
        return []

    @abstractmethod
    def get_supported_image_provider_types(self):
        raise NotImplemented
