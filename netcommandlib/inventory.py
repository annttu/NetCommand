import logging

logger = logging.getLogger("inventory")


class Inventory(object):

    def __init__(self):
        self.hosts = {}
        self.groups = {}
        self.sources = {}

    @classmethod
    def load_from_dict(cls, inventory):
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
