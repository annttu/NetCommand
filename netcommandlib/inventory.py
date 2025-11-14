import functools
import logging

logger = logging.getLogger("inventory")

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
}

HOST_VALIDATORS={
    "hostname": required(string),
}



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
    def _load_group(cls, inventory, path=None, parent_opts=None):
        hosts = {"hosts": {}, "groups": {}}
        if not path:
            path = []
        if parent_opts is None:
            parent_opts = {}
        opts = {}
        opts.update(parent_opts)
        opts.update(inventory.get("opts", {}))
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
