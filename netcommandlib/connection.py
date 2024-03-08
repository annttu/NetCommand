import os
import socket
import time
from enum import Enum

import paramiko
from abc import ABCMeta, abstractmethod
import logging

logger = logging.getLogger("Connection")
logging.getLogger("paramiko.transport").setLevel(logging.ERROR)


class ConnectionError(Exception):
    pass


class CommandError(Exception):
    pass


class Connection(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def run(self, command):
        raise NotImplemented()

    @abstractmethod
    def command(self, command):
        raise NotImplemented()

    @abstractmethod
    def upload_file(self, buffer, filename):
        raise NotImplemented()

    @abstractmethod
    def close(self):
        raise NotImplemented()

    @abstractmethod
    def reopen(self):
        raise NotImplemented()

    @abstractmethod
    def expect_disconnect(self):
        raise NotImplemented()

    @abstractmethod
    def get_address(self):
        raise NotImplemented()


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

class Actions(Enum):
    BREAK = "break"


class SSHConnection(Connection):
    def __init__(self, address, username="admin", password="", key_filename=None, key_password=None, port=22, prompt=">"):
        self.address = address
        self.port = port
        self._username = username
        self._password = password
        self._key_filename = key_filename
        self._key_password = key_password
        self._sftp = None
        self._connection = None
        self.prompt = prompt
        self._initial_prompt = prompt
        self._channel = None
        self._at_prompt = False

        if 'SSH_AUTH_SOCK' in os.environ:
            del os.environ['SSH_AUTH_SOCK']

        logger.debug("Opening SSH connection to %s@%s" % (username, address))
        self._connection = self._connect()

    @property
    def connection(self):
        if not self._connection:
            self._connection = self._connect()
        return self._connection

    def _connect(self):
        logger.debug(f"Opening new SSH connection to {self._username}@{self.address}")
        connection = paramiko.SSHClient()
        if os.path.isfile(os.path.expanduser('~/.ssh/known_hosts')):
            connection.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
        connection.set_missing_host_key_policy(
            paramiko.AutoAddPolicy())
        connection._policy = paramiko.WarningPolicy()
        kwargs = {
            'username': self._username,
            "allow_agent": False,
            'look_for_keys': False,
            # Devices are picky about pubkeys
            "disabled_algorithms": {
                # Disable sha2 hashes, don't work properly with non openssh servers
                # "pubkeys": [
                #     "rsa-sha2-512",
                #     "rsa-sha2-256",
                #     "ecdsa-sha2-nistp256",
                #     "ecdsa-sha2-nistp384",
                #     "ecdsa-sha2-nistp521",
                # ],
            },
            'port': self.port,
        }
        if self._key_filename is not None:
            try:
                rsa_key = paramiko.RSAKey.from_private_key_file(self._key_filename)
            except paramiko.ssh_exception.PasswordRequiredException:
                if not self._key_password:
                    raise RuntimeError("SSH key requires password but password not provided")
                rsa_key = paramiko.RSAKey.from_private_key_file(self._key_filename, password=self._key_password)
            kwargs['pkey'] = rsa_key
        else:
            kwargs['password'] = self._password
        logger.debug("KWARGS %s" % (kwargs,))
        connection.connect(self.address, timeout=30, **kwargs)
        logger.debug("New SSH connection to %s@%s is now open" % (self._username, self.address))
        return connection

    @property
    def sftp(self):
        if not self._sftp:
            self._sftp = paramiko.SFTPClient.from_transport(self.connection.get_transport())
        return self._sftp

    def upload_file(self, buffer, filename):
        return self.sftp.putfo(buffer, filename)

    def run(self, command, timeout=5):
        logger.debug("SSH Command: %s", command)
        response = self.connection.exec_command(command, timeout=timeout)
        stderr = response[2].read().decode("utf-8")
        stdout = response[1].read().decode("utf-8")
        return stdout, stderr

    def command(self, command, ignore_errors=False, ignore_warnings=False, ignore_duplicate=False):
        (stdout, stderr) = self.run(command)

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
        logger.debug("SSH:\n%s", stdout)
        return stdout

    def close(self):
        self.connection.close()

    def reopen(self, timeout=900):
        if wait_connection(self.address, self.port, timeout=timeout):
            self._connection = self._connect()
            return self
        raise ConnectionError("Failed to reopen connection")

    def expect_disconnect(self, timeout=900):
        self.close_channel()
        self.close()
        time.sleep(5)
        self.reopen(timeout=timeout)

    @classmethod
    def from_env(cls, env):
        return SSHConnection(env['ssh_ip'], username=env['ssh_username'], password=env.get("ssh_password", None),
                             key_filename=env.get("ssh_key_filename", None),
                             key_password=env.get("ssh_key_password", None))

    @property
    def channel(self):
        if not self._channel:
            self._channel = self.connection.invoke_shell()
        return self._channel

    def _wait_prompt(self, timeout=5, prompt=None):
        if self._at_prompt:
            return
        data = ""
        if not prompt:
            prompt = self.prompt
        logger.debug(f"Waiting for prompt '{prompt}'")
        self.channel.settimeout(timeout)
        while True:
            char = self.channel.recv(nbytes=len(self.prompt))
            data += char.decode("utf-8")
            logger.debug(f"prompt data {data.encode('utf-8')}")
            if data.endswith(prompt) or data.endswith(prompt + " "):
                break
        self.channel.settimeout(None)
        self._at_prompt = True
        logger.debug(f"prompt: '{data.encode('utf-8')}'")

    def set_prompt(self, prompt):
        self.prompt = prompt

    def reset_prompt(self):
        self.prompt = self._initial_prompt

    def run_interactive(self, command, timeout=5, row_callback=None, end_of_line=None):
        if not end_of_line:
            end_of_line = "\r\n"
        end_of_line = end_of_line.encode("utf-8")
        logger.debug("SSH Interactive Command: %s", command)
        self._wait_prompt(timeout=timeout)
        self.channel.settimeout(timeout)
        binary_command = command.encode("utf-8")
        self.channel.sendall(binary_command + end_of_line)
        self._at_prompt = False
        # wait until we see what we typed
        #logger.debug("Waiting for command echo")
        # data = b""
        # while True:
        #     data += self.channel.recv(nbytes=1)
        #     logger.debug(f"echo data: {data}")
        #     if binary_command in data:
        #         break
        # logger.debug("Actual command echoed: %s" % data)
        data = b""
        times_sleep = 0
        while True:
            logger.debug(f"Data received: {data}")
            new_data = b''
            if self.channel.recv_ready():
                time.sleep(0.2)
                new_data = self.channel.recv(nbytes=8192)
                data += new_data
            elif self.channel.recv_stderr_ready():
                time.sleep(0.2)
                new_data = self.channel.recv_stderr(nbytes=8192)
                data += new_data
            else:
                # break
                time.sleep(1)
                times_sleep += 1
                if times_sleep > timeout:
                    raise TimeoutError
                logger.debug(f"No new data received")
                continue
            if len(data) > len(command) + 1:
                if data.endswith(self.prompt.encode("utf-8")) or data.endswith(self.prompt.encode("utf-8") + b" "):
                    self._at_prompt = True
                    break
                elif row_callback:
                    break_out = False
                    for row in new_data.decode("utf-8").strip().splitlines():
                        action = row_callback(row)
                        if action == Actions.BREAK:
                            break_out = True
                            break
                        elif isinstance(action, str):
                            if not action.endswith("\n"):
                                action += "\n"
                            action = action.encode("utf-8")
                            self.channel.sendall(action)
                    if break_out:
                        break

        self.channel.settimeout(None)
        data = data.decode("utf-8")
        # Strip prompts from data
        if self._at_prompt:
            data = data[len(command) + 1:data.rfind("\n")]
        logger.debug("Data for command %s:\n%s" % (command, data))
        return data

    def close_channel(self):
        if self._channel:
            self._channel.close()
            self._channel = None
            self.reset_prompt()
        self._at_prompt = False

    def get_address(self):
        return self.address

def connection_from_opts(opts):
    kwargs = {
        'address': opts["hostname"],
    }
    for key, value in {'password': "password", 'username': "username", 'port': "port",
                       "ssh_key_password": 'key_password'}.items():
        if key in opts:
            kwargs[value] = opts[key]
    for key, value in {"ssh_key": 'key_filename'}.items():
        if key in opts:
            kwargs[value] = os.path.expanduser(opts[key])
    return kwargs


def check_connection(address, port=22):
    """
    Check TCP connection
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((address, port))
    except socket.timeout:
        sock.settimeout(None)
        sock.close()
        return False
    except ConnectionRefusedError:
        sock.settimeout(None)
        sock.close()
        return False
    except OSError:
        sock.settimeout(None)
        sock.close()
        return False
    sock.settimeout(None)
    sock.close()
    return True


def wait_connection(address, port=22, timeout=900):
    """
    Wait for service to become available on given ip and port
    """
    rounds = timeout // 10
    for i in range(rounds):
        if check_connection(address, port):
            logger.info(f"Connection to {address}:{port} is open")
            return True
        # To prevent accidental busy loops
        time.sleep(5)
        if i % 5 == 0:
            logger.info(f"Waiting for {address}:{port} to respond")
    return False
