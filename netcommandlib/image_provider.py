import glob
import logging
import os

import requests as requests

from netcommandlib.connection import SSHConnection
from netcommandlib import image

logger = logging.getLogger("image_provider")


class ImageProvider(object):
    type = "generic"

    def find_image(self, filename):
        raise NotImplementedError()


class LocalImageProvider(object):
    type = "local"

    def __init__(self, directory):
        self.directory = os.path.expanduser(directory)

    def find_image(self, filename, **kwargs):
        files = glob.glob(os.path.join(self.directory, filename))

        if len(files) == 0:
            logger.error(f"LocalImageProvider: Failed to find upgrade image {filename}")
            return None
        elif len(files) > 1:
            logger.error(f"LocalImageProvider: Multiple files found matching {filename} in path {self.directory}")
            return None

        return image.LocalImage(path=files[0], **kwargs)


class HTTPImageProvider(object):
    type = "http"

    def __init__(self, server, path="", port=80,  username=None, password=None, protocol="http"):
        self.server = server
        self.username = username
        self.password = password
        self.path = path.strip("/")
        self.port = port
        self.protocol = protocol

    def check_exists(self, url):
        r = requests.head(url=url)

        logger.debug(f"URL {url} returned {r.status_code}")
        if r.status_code == 200:
            return True
        return False

    def find_image(self, filename, **kwargs):
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        url = f"{self.protocol}://{auth}{self.server}/{self.path}/{filename}"

        if not self.check_exists(url):
            return None

        return image.HTTPImage(
            protocol=self.type,
            server=self.server,
            path=f"{self.path}/{filename}",
            port=self.port,
            username=self.username,
            password=self.password,
            **kwargs
        )


class HTTPSImageProvider(HTTPImageProvider):
    type = "https"

    def __init__(self, server, path="", port=443,  username=None, password=None, protocol="https"):
        super().__init__(server=server, path=path, port=port, username=username, password=password, protocol=protocol)


class SCPImageProvider(ImageProvider):
    type = "scp"

    def __init__(self, server, path="", port=22, username=None, password=None):
        self.server = server
        self.username = username
        self.password = password
        self.path = path.strip("/")
        self.port = port
        self.protocol = self.type

    def check_exists(self, url, filename):
        connection = SSHConnection(self.server, username=self.username, password=self.password, port=self.port)
        try:
            stat = connection.sftp.stat(filename)
            logger.debug(f"SCP {url} returned {stat}")
            return True
        except FileNotFoundError:
            return False

    def find_image(self, filename, **kwargs):
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        url = f"{self.protocol}://{auth}{self.server}/{self.path}/{filename}"

        if not self.check_exists(url, filename):
            return None

        return image.NetworkImage(protocol=self.protocol, server=self.server, path=f"{self.path}/{filename}",
                                  port=self.port, username=self.username, password=self.password, **kwargs)


IMAGE_PROVIDERS = {
    "local": LocalImageProvider,
    "http": HTTPImageProvider,
    "https": HTTPSImageProvider,
    "scp": SCPImageProvider,
}
