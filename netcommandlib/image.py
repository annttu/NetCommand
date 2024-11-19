import io
import os


class GenericImage(object):
    def __init__(self, version, platform):
        self.platform = platform
        self.version = version


class LocalImage(GenericImage):
    def __init__(self, path, version, platform):
        super().__init__(version=version, platform=platform)
        self.path = path
        self.filename = os.path.basename(self.path)

    def as_bytes(self):
        with open(self.path, 'rb') as f:
            buffer = io.BytesIO(f.read())
            buffer.seek(0)
            return buffer


class NetworkImage(GenericImage):
    def __init__(self, protocol, server, path, username, password, port, version, platform):
        super().__init__(version=version, platform=platform)
        self.protocol = protocol
        self.server = server
        self.path = path
        self.username = username
        self.password = password
        self.port = port
        self.filename = os.path.basename(self.path)

    def validate_protocol(self):
        return True

    def get_url(self, credentials=True, skip_port=False):
        auth = ""
        if self.username and self.password and credentials is True:
            auth = f"{self.username}:{self.password}@"
        elif self.username:
            auth = f"{self.username}@"
        port = ""
        if self.port and not skip_port:
            port = f":{self.port}"
        return f"{self.protocol}://{auth}{self.server}{port}/{self.path.lstrip('/')}"


class HTTPImage(NetworkImage):
    def validate_protocol(self):
        return self.protocol in ["http", "https"]