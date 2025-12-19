import tempfile
import os.path
from unittest import TestCase
from unittest.mock import patch

import requests_mock

from netcommandlib.image import HTTPImage, LocalImage, NetworkImage
from netcommandlib.image_provider import HTTPSImageProvider, HTTPImageProvider, LocalImageProvider, SCPImageProvider


class TestHTTPSImageProvider(TestCase):
    PROVIDER = HTTPSImageProvider
    def test_find_image(self):
        with requests_mock.Mocker() as m:
            m.head('https://localhost:443/path/test.bin', text='data')
            provider = HTTPSImageProvider(server="localhost", path="path")
            image = provider.find_image("test.bin", version="1", platform="unknown")
            assert isinstance(image, HTTPImage)
            assert image.get_url() == "https://localhost:443/path/test.bin"

    def test_find_image_with_template_vars(self):
        with requests_mock.Mocker() as m:
            m.head('https://localhost:443/arm/version-7.20.0/test.bin', text='data')
            provider = HTTPSImageProvider(server="localhost", path="%(platform)s/version-%(version)s")
            image = provider.find_image("test.bin", version="7.20.0", platform="arm")
            assert isinstance(image, HTTPImage)
            assert image.get_url() == "https://localhost:443/arm/version-7.20.0/test.bin"


class TestHTTPImageProvider(TestCase):
    def test_find_image(self):
        with requests_mock.Mocker() as m:
            m.head('http://localhost:80/path/test.bin', text='data')
            provider = HTTPImageProvider(server="localhost", path="path")
            image = provider.find_image("test.bin", version="1", platform="unknown")
            assert isinstance(image, HTTPImage)
            assert image.get_url() == "http://localhost:80/path/test.bin"


class TestLocalImageProvider(TestCase):
    def test_find_image(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with open(os.path.join(tempdir, "test.bin"), "w") as f:
                f.write("test")
            provider = LocalImageProvider(directory=tempdir)
            image = provider.find_image("test.bin", version="1", platform="unknown")
            assert isinstance(image, LocalImage)
            with image.as_bytes() as data:
                assert data.read() == b"test"


class TestSCPImageProvider(TestCase):
    @patch('netcommandlib.image_provider.SCPImageProvider.check_exists')
    def test_find_image(self, mocker):
        provider = SCPImageProvider(server="localhost", path="path")
        image = provider.find_image("test.bin", version="1", platform="unknown")
        assert isinstance(image, NetworkImage)
        assert image.get_url() == "scp://localhost:22/path/test.bin"
        provider.check_exists.assert_called_once_with('scp://localhost:22/path/test.bin')