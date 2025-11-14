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
    def run(self, command, timeout=5):
        raise NotImplementedError()

    @abstractmethod
    def run_interactive(self, command, timeout=5, row_callback=None, end_of_line=None):
        raise NotImplementedError()

    @abstractmethod
    def upload_file(self, buffer, filename):
        raise NotImplementedError()

    @abstractmethod
    def close(self):
        raise NotImplementedError()

    @abstractmethod
    def reopen(self):
        raise NotImplementedError()

    @abstractmethod
    def connect(self):
        raise NotImplementedError()

    @abstractmethod
    def expect_disconnect(self):
        raise NotImplementedError()

    @abstractmethod
    def get_address(self):
        raise NotImplementedError()


class Actions(Enum):
    BREAK = "break"


def cli_run_interactive(send_function, receive_function, binary_command, prompt, timeout=5, row_callback=None):
    send_function(binary_command)
    return wait_prompt_with_callback(
        send_function,
        receive_function,
        prompt,
        timeout=timeout,
        row_callback=row_callback,
        min_input_length=len(binary_command) + 1
    )


def wait_prompt_with_callback(
        send_function,
        receive_function,
        prompt,
        timeout=5,
        row_callback=None,
        min_input_length=0,
        encoding="utf-8"
):
    at_prompt = False
    data = ""
    times_sleep = 0
    while True:
        logger.debug(f"Data received: {data}")
        new_data = receive_function(8192)
        if new_data:
            data += new_data.decode(encoding, errors="ignore")
        else:
            # break
            time.sleep(1)
            times_sleep += 1
            if times_sleep > timeout:
                raise TimeoutError
            logger.debug("No new data received")
            continue
        if len(data) > min_input_length:
            if data.endswith(prompt) or data.endswith(prompt + " "):
                at_prompt = True
                break
            elif row_callback:
                break_out = False
                for row in data.strip().splitlines():
                    action = row_callback(row)
                    logger.debug(f"Row '{row}' callback action {action}")
                    if action == Actions.BREAK:
                        break_out = True
                        break
                    elif isinstance(action, str):
                        send_function(action.encode(encoding))
                if break_out:
                    break
    # Strip prompts from data
    if at_prompt:
        data = data[min_input_length:data.rfind("\n")]
    logger.debug(f"Input data:\n{data}")
    logger.debug(f"At prompt {at_prompt}")
    return data, at_prompt


class TelnetConnection(Connection):
    """
    TODO: Support for Telnet NVT and control character processing
    """

    def __init__(self, address, username="admin", password="", port=23, prompt=">", login_dialog=None):
        self.address = address
        self.port = port
        self._username = username
        self._password = password
        self._connection = None
        self._login_dialog = login_dialog
        self.prompt = prompt
        self._initial_prompt = prompt
        self._at_prompt = False
        self._channel = None
        self.end_of_line = "\r\n"
        self.encoding = "utf-8"

    @property
    def channel(self):
        if not self._channel:
            self.connect()
        return self._channel

    def connect(self):
        logger.info(f"Connecting to {self.address}:{self.port}")
        res = socket.getaddrinfo(self.address, self.port, socket.AF_INET, socket.SOCK_STREAM)
        if len(res) < 1:
            logger.critical(f"Failed to resolve connection for {self.address}:{self.port}")
            raise ConnectionError(f"Failed to resolve connection for {self.address}:{self.port}")
        af, socket_type, proto, canonical_name, sa = res[0]
        if len(res) > 1:
            logger.warning(f"Got more than one result from DNS, using first: {sa}")
        try:
            self._channel = socket.socket(af, socket.SOCK_STREAM)
        except OSError:
            logger.exception("Failed to open socket")
            self._channel = None
            raise ConnectionError("Failed to open socket")
        try:
            self.set_timeout(30)
            self._channel.connect(sa)
            logger.info(f"Connected to {self.address}:{self.port}")
            self.set_timeout(None)
        except OSError:
            self._channel.close()
            self._channel = None
            raise ConnectionError("Failed to open connection")
        if self._login_dialog:
            self.set_timeout(30)
            # self._send(self.end_of_line.encode("utf-8"))
            data, self._at_prompt = wait_prompt_with_callback(
                self._send,
                self._receive,
                prompt=self.prompt,
                timeout=30,
                row_callback=self._login_dialog(self._username, self._password),
                min_input_length=1,
            )
            self.set_timeout(None)
            if not self._at_prompt:
                # login failed?
                raise RuntimeError("Login failed, login process didn't end up in prompt")
        else:
            raise RuntimeError("No way to login, please check model's login_dialog function")

    def run(self, command, timeout=5):
        return self.run_interactive(command, timeout=timeout)

    def run_interactive(self, command, timeout=5, row_callback=None, end_of_line=None):
        if not end_of_line:
            end_of_line = self.end_of_line
        end_of_line = end_of_line.encode(self.encoding)
        logger.debug("Telnet Interactive Command: %s", command)
        self._wait_prompt(timeout=timeout)
        binary_command = command.encode(self.encoding)

        self.set_timeout(timeout)
        data, self._at_prompt = cli_run_interactive(
            self._send,
            self._receive,
            binary_command + end_of_line,
            self.prompt,
            timeout=timeout,
            row_callback=row_callback
        )
        self.set_timeout(None)
        return data

    def upload_file(self, buffer, filename):
        raise NotImplementedError()

    def close(self):
        if self._channel:
            self._channel.close()

    def reopen(self):
        if self._channel:
            self._channel.close()
        self._connect()

    def expect_disconnect(self):
        self.close()
        time.sleep(5)
        self.reopen()

    def _send(self, command):
        logger.debug(f"Raw output: {command}")
        self._channel.sendall(command)

    def _receive(self, nbytes):
        data = self._channel.recv(nbytes)
        logger.debug(f"Raw input: {data}")
        return data

    def _wait_prompt(self, timeout=5, prompt=None):
        logger.debug(f"wait_prompt: at_prompt: {self._at_prompt}")
        if self._at_prompt:
            return
        data = ""
        if not prompt:
            prompt = self.prompt
        logger.debug(f"Waiting for prompt '{prompt}'")
        self.set_timeout(timeout)
        while True:
            char = self.channel.recv(len(self.prompt))
            if len(char) == 0:
                time.sleep(0.1)
                continue
            data += char.decode(self.encoding, errors="replace")
            logger.debug(f"prompt data {data.encode(self.encoding)}")
            if data.endswith(prompt) or data.endswith(prompt + " "):
                break
        self.set_timeout(None)
        self._at_prompt = True
        logger.debug(f"prompt: '{data.encode(self.encoding)}'")

    def set_timeout(self, timeout):
        self.channel.settimeout(timeout)


class SSHConnection(Connection):
    def __init__(
            self,
            address,
            username="admin",
            password="",
            key_filename=None,
            key_password=None,
            port=22,
            prompt=">",
            login_dialog=None,
            jump_host=None,
    ):
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
        self.jump_host = jump_host
        self._jump_host_connection = None


        if 'SSH_AUTH_SOCK' in os.environ:
            del os.environ['SSH_AUTH_SOCK']

        logger.debug("Opening SSH connection to %s@%s" % (username, address))
        self.connect()

    @property
    def connection(self):
        if not self._connection:
            self.connect()
        return self._connection

    def _connect(self):
        logger.debug(f"Opening new SSH connection to {self._username}@{self.address}:{self.port}")
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
        if self.jump_host:
            logger.debug(f"Connecting to SSH jumping host '{self.jump_host}'")
            if not self._jump_host_connection:
                self._jump_host_connection = SSHConnection(
                    address=self.jump_host["hostname"],
                    username=self.jump_host.get("username", self._username),
                    password=self.jump_host.get("password", self._password),
                    key_filename=self.jump_host.get("ssh_key", self._key_filename),
                    key_password=self.jump_host.get("ssh_key_password", self._key_password),
                    jump_host=self.jump_host.get("jump_host", None),
                )
            try:
                self._jump_host_connection.connect()
                jump_host_sock = self._jump_host_connection.connection.get_transport().open_channel(
                    'direct-tcpip', (self.address, self.port), ('', 0)
                )
                kwargs["sock"] = jump_host_sock
            except ConnectionError as exc:
                raise ConnectionError(f"Failed to open SSH connection to jump host "
                                      f"{self._username}@{self.jump_host}:{self.port}: {exc}")
        logger.debug("KWARGS %s" % (kwargs,))
        try:
            connection.connect(self.address, timeout=30, **kwargs)
        except socket.timeout as exc:
            raise ConnectionError(f"Failed top open SSH connection to "
                                  f"{self._username}@{self.address}:{self.port}: {exc}")
        logger.debug("New SSH connection to %s@%:%d is now open", self._username, self.address, self.port)
        return connection

    def connect(self):
        self._connection = self._connect()

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

    def close(self):
        self.connection.close()
        if self._jump_host_connection:
            self._jump_host_connection.close()

    def reopen(self, timeout=900):
        time_start = time.time()
        if wait_connection(self.address, self.port, timeout=timeout):
            logger.info("Reconnecting to %s:%d" % (self.address, self.port))
            while time.time() - timeout < time_start:
                try:
                    self._connection = self._connect()
                    return self
                except ConnectionError as exc:
                    logger.debug("Creating new connection failed: %s" % exc)
        raise ConnectionError("Failed to reopen connection: timeout")

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

    def set_timeout(self, timeout):
        self.channel.settimeout(timeout)

    def _receive(self, nbytes):
        data = b""
        if self.channel.recv_ready():
            time.sleep(0.2)
            new_data = self.channel.recv(nbytes=nbytes)
            data += new_data
        elif self.channel.recv_stderr_ready():
            time.sleep(0.2)
            new_data = self.channel.recv_stderr(nbytes=nbytes)
            data += new_data
        return data

    def _send(self, data):
        return self.channel.sendall(data)

    def _wait_prompt(self, timeout=5, prompt=None):
        if self._at_prompt:
            return
        data = ""
        if not prompt:
            prompt = self.prompt
        logger.debug(f"Waiting for prompt '{prompt}'")
        self.set_timeout(timeout)
        while True:
            char = self.channel.recv(nbytes=len(self.prompt))
            data += char.decode("utf-8")
            logger.debug(f"prompt data {data.encode('utf-8')}")
            if data.endswith(prompt) or data.endswith(prompt + " "):
                break
        self.set_timeout(None)
        self._at_prompt = True
        logger.debug(f"prompt: '{data.encode('utf-8')}'")

    def set_prompt(self, prompt):
        self.prompt = prompt

    def reset_prompt(self):
        self.prompt = self._initial_prompt

    def run_interactive(self, command, timeout=5, row_callback=None, end_of_line=None, dry_run=False):
        if not end_of_line:
            end_of_line = "\r\n"
        end_of_line = end_of_line.encode("utf-8")
        logger.debug("SSH Interactive Command: %s", command)
        if dry_run:
            return None
        self._wait_prompt(timeout=timeout)
        self.set_timeout(timeout)
        binary_command = command.encode("utf-8")

        data, self._at_prompt = cli_run_interactive(
            self._send,
            self._receive,
            binary_command + end_of_line,
            self.prompt,
            row_callback=row_callback
        )
        self.set_timeout(None)

        return data

    def close_channel(self):
        if self._channel:
            self._channel.close()
            self._channel = None
            self.reset_prompt()
        self._at_prompt = False

    def get_address(self):
        return self.address


def connection_from_opts(opts, login_dialog=None):
    method = 'ssh'
    kwargs = {
        'address': opts["hostname"],
        'login_dialog': login_dialog,
    }
    for key, value in {'password': "password", 'username': "username", 'port': "port",
                       "ssh_key_password": 'key_password', 'prompt': 'prompt'}.items():
        if key in opts:
            kwargs[value] = opts[key]
    for key, value in {"ssh_key": 'key_filename'}.items():
        if key in opts:
            kwargs[value] = os.path.expanduser(opts[key])

    if 'method' in opts:
        method = opts['method']

    if method == 'ssh':
        if "ssh_jump_host" in opts:
            kwargs["jump_host"] = opts["ssh_jump_host"]
        return SSHConnection(**kwargs)
    elif method == 'telnet':
        return TelnetConnection(**kwargs)
    raise ValueError(f"Invalid method {method}")


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
