import glob
import logging
import os

import requests as requests

from netcommandlib.connection import SSHConnection
from netcommandlib.image import LocalImage, NetworkImage, HTTPImage

logger = logging.getLogger("image_provider")


class ImageProvider(object):
    type = "generic"

    def find_image(self, filename, version, platform):
        raise NotImplementedError()


class LocalImageProvider(ImageProvider):
    type = "local"

    def __init__(self, directory):
        self.directory = os.path.expanduser(directory)

    def __str__(self):
        return f"LocalImageProvider {self.directory}/**/%(filename)s"

    def find_image(self, filename, version, platform):
        files = glob.glob(os.path.join(self.directory, filename))

        if len(files) == 0:
            logger.error(f"LocalImageProvider: Failed to find upgrade image {filename}")
            return None
        elif len(files) > 1:
            logger.error(f"LocalImageProvider: Multiple files found matching {filename} in path {self.directory}")
            return None

        return LocalImage(path=files[0], version=version, platform=platform)


class NetworkImageProvider(ImageProvider):
    def __init__(self, server, protocol, path, port, username=None, password=None):
        self.server = server
        self.username = username
        self.password = password
        self.path = path.strip("/")
        self.port = port
        self.protocol = protocol

    def __str__(self):
        return f"NetworkImageProvider {self.protocol}://***@{self.server}:{self.port}/{self.path}/%(filename)s"

    def _format_path(self, filename, version, platform):
        path = f"{self.path}/{filename}"
        if version or platform:
            path = path % {"version": version, "platform": platform}
        return path

    def _get_image(self, filename, version, platform) -> NetworkImage:
        return NetworkImage(
            protocol=self.protocol,
            server=self.server,
            path=self._format_path(filename, version=version, platform=platform),
            port=self.port,
            username=self.username,
            password=self.password,
            version=version,
            platform=platform
        )

    @classmethod
    def check_exists(cls, image):
        raise NotImplementedError()

    def find_image(self, filename, version, platform, **kwargs):
        img = self._get_image(filename, version, platform)

        if not self.check_exists(img):
            return None

        return img


class HTTPImageProvider(NetworkImageProvider):
    type = "http"

    def __init__(self, server, path="", port=80, username=None, password=None, protocol="http"):
        super().__init__(
            protocol=protocol,
            server=server,
            path=path,
            port=port,
            username=username,
            password=password
        )

    @classmethod
    def check_exists(cls, image: HTTPImage):
        url = image.get_url()
        r = requests.head(url)

        logger.debug(f"URL {url} returned {r.status_code}")
        if r.status_code == 200:
            return True
        return False

    def _get_image(self, filename, version, platform, **kwargs) -> NetworkImage:
        return HTTPImage(
            protocol=self.protocol,
            server=self.server,
            path=self._format_path(filename, version, platform),
            port=self.port,
            username=self.username,
            password=self.password,
            version=version,
            platform=platform,
        )


class HTTPSImageProvider(HTTPImageProvider):
    type = "https"

    def __init__(self, server, path="", port=443,  username=None, password=None):
        super().__init__(server=server, path=path, port=port, username=username, password=password, protocol="https")


class SCPImageProvider(NetworkImageProvider):
    type = "scp"

    def __init__(self, server, path="", port=22, username=None, password=None):
        super().__init__(
            server = server,
            username = username,
            password = password,
            path = path.strip("/"),
            port = port,
            protocol = "scp",
        )

    @classmethod
    def check_exists(cls, image: NetworkImage):
        url = image.get_url()
        connection = SSHConnection(image.server, username=image.username, password=image.password, port=image.port)
        try:
            stat = connection.sftp.stat(image.path)
            logger.debug(f"SCP {url} returned {stat}")
            return True
        except FileNotFoundError:
            return False


IMAGE_PROVIDERS = {
    "local": LocalImageProvider,
    "http": HTTPImageProvider,
    "https": HTTPSImageProvider,
    "scp": SCPImageProvider,
}
