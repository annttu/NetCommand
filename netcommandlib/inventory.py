import functools
import json
import logging
import subprocess
from typing import Dict

logger = logging.getLogger("inventory")
OP_PATH = "/opt/homebrew/bin/op"


def required(func):
    @functools.wraps(func)
    def wrapper(value, path=None):
        if not path:
            path=""
        if value is None:
            raise ValueError(f"Required value is empty in path {path}")
        return value
    return wrapper


def require_type(value, value_type, path=None):
    if not path:
        path=""
    if value is None:
        return None
    if isinstance(value, value_type):
        return value
    raise ValueError(f"Value is not {value_type} in path {path}")


def string(value, path=None):
    require_type(value, str, path=path)


def integer(value, path=None):
    require_type(value, int, path=path)


def mapping(options, path=None):
    mapping_path = path if path is not None else ""
    def mapping_wrapper(value, path=None):
        if path is None:
            path=mapping_path
        else:
            path=f"{path}.{mapping_path}"
        if not isinstance(value, dict):
            raise TypeError(f"Value {value} is not a mapping in {path}")
        for key, value in value.items():
            if key not in options:
                raise ValueError(f"Key {key} is not a valid option in {path}")
            options[key](value, path=f"{path}.{key}")
        return value
    return mapping_wrapper


JUMP_HOST_VALIDATORS={
    "hostname": string,
    "username": string,
    "password": string,
    "op_item": string,
    "op_account": string,
}


OPTS_VALIDATORS={
    "model": string,
    "username": string,
    "password": string,
    "port": integer,
    "ssh_key_password": string,
    "ssh_key": string,
    "prompt": string,
    "ssh_jump_host": mapping(JUMP_HOST_VALIDATORS),
    "op_item": string,
    "op_account": string,
}

HOST_VALIDATORS={
    "hostname": required(string),
}


class OP(object):
    @classmethod
    def get_item(cls, item_id, account_id=None) -> Dict[str, str]:
        args = [OP_PATH, "item", "get", item_id, "--reveal", "--format", "json"]
        if account_id:
            args.append("--account")
            args.append(account_id)
        logger.debug(f"Executing {' '.join(args)}")
        try:
            result = subprocess.run(args, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.error(f"1Password CLI returned an error, failed to get item {item_id}")
            raise RuntimeError(f"failed to fetch 1password item {item_id}")
        item = json.loads(result.stdout.decode("utf-8"))

        fields = {}
        for field in item["fields"]:
            if 'value' in field:
                fields[field["label"]] = field["value"]
        return fields


class Inventory(object):
    def __init__(self):
        self.hosts = {}
        self.groups = {}
        self.sources = {}

    @classmethod
    def load_from_dict(cls, inventory):
        cls.validate_options(inventory)
        inv = Inventory()
        hosts = cls._load_group(inventory)
        inv.hosts = hosts["hosts"]
        inv.groups = hosts["groups"]
        inv.sources = inventory.get("sources", {})
        return inv

    @classmethod
    def _load_host(cls, host):
        return cls._load_password(host)

    @classmethod
    def _load_password(cls, host):
        op_item = host.get("op_item")
        op_account = host.get("op_account")
        if op_item:
            op_item = OP.get_item(op_item, op_account)
            if 'password' in op_item:
                host["password"] = op_item["password"]
                del host["op_item"]
                del host["op_account"]
                return host
            else:
                raise ValueError(f"Failed to find password for host {host["hostname"]} with op_item {op_item}")

    @classmethod
    def _load_group(cls, inventory, path=None, parent_opts=None):
        hosts = {"hosts": {}, "groups": {}}
        if not path:
            path = []
        if parent_opts is None:
            parent_opts = {}
        opts = {}
        opts.update(inventory.get("opts", {}))
        opts.update(parent_opts)

        if 'ssh_jump_host' in opts:
            cls._load_host(opts["ssh_jump_host"])
        for group_name, items in inventory.get("groups", {}).items():
            group_data = cls._load_group(items, path + [group_name], parent_opts=opts)
            hosts["hosts"].update(group_data["hosts"])
            hosts["groups"].update(group_data["groups"])
        for hostname, items in inventory.get("hosts", {}).items():
            # this is a host
            if items is None:
                items = {}
            host_items = {}
            host_items.update(opts)
            host_items.update(items)
            if 'hostname' not in host_items:
                host_items["hostname"] = hostname
            host_items["groups"] = path
            cls._load_host(host_items)
            hosts["hosts"][hostname] = host_items
        return hosts

    @classmethod
    def validate_options(cls, inventory):
        if not isinstance(inventory, dict):
            raise ValueError("Inventory must be a dictionary")
        mapping(OPTS_VALIDATORS, "opts")(inventory.get("opts", {}))
        for group_name, group in inventory.get("groups", {}).items():
            mapping(OPTS_VALIDATORS, path=f"groups.{group_name}.opts")(group.get("opts", {}))
            for host_name, host in group.get("hosts", {}).items():
                mapping(HOST_VALIDATORS, path=f"groups.{group_name}.hosts.{host_name}")(host)

    def filter_hosts(self, global_filter):
        out = {}
        for hostname, opts in self.hosts.items():
            found = False
            if hostname in global_filter:
                found = True
            for group in opts["groups"]:
                if group in global_filter:
                    found = True
            if not found:
                logger.debug(f"Skipping host {hostname}, don't match limit")
                continue
            out[hostname] = opts
        return out
