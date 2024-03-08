#!/usr/bin/env python3

"""
NetCommand
CLI device batch command tool.
"""

import getpass
import logging
import os.path
from typing import Dict, Union

import yaml
import argparse

import models
from models.model import Model
from netcommandlib.connection import SSHConnection, connection_from_opts
from netcommandlib.image_provider import IMAGE_PROVIDERS
from netcommandlib.inventory import Inventory
from netcommandlib.upgrade import generic_upgrade

logger = logging.getLogger("batch_update")


def get_model(hostname: str, opts: Dict) -> Union[Model, None]:
    model_name = opts.get("model", "unknown")
    if model_name not in models.MODELS:
        logger.error(f"Host {hostname} model {model_name} is not supported")
        return None
    kwargs = connection_from_opts(opts)

    kwargs["prompt"] = models.MODELS[model_name].PROMPT
    connection = SSHConnection(**kwargs)

    model = models.MODELS[model_name](connection=connection)
    return model


def update(args, hostname, opts, image_providers, dry_run=False):
    result = {
        "status": "FAILED"
    }
    logger.info(f"Running update to host {hostname}")
    logger.debug(f"Opts: {opts}")

    model = get_model(hostname, opts)
    if not model:
        return False

    current_software_version = model.get_software_version()
    current_firmware_version = model.get_firmware_version()

    platform = model.get_platform()

    result.update({
        "initial_software_version": current_software_version,
        "current_software_version": current_software_version,
        "initial_firmware_version": current_firmware_version,
        "current_firmware_version": current_firmware_version,
    })

    filename = model.get_upgrade_package_name(args.version)
    image = None
    for image_provider in image_providers:
        if image_provider.type not in model.get_supported_image_provider_types():
            continue
        image = image_provider.find_image(filename, version=args.version, platform=platform)
        if image:
            break

    if not image:
        logger.error(
            f"Failed to find upgrade image '{filename}' for {hostname} {args.version} {model.get_platform()}")
        return result

    extra_images = []
    for extra_image_filename in model.get_extra_package_names(args.version):
        extra_image = None
        for image_provider in image_providers:
            if image_provider.type not in model.get_supported_image_provider_types():
                continue
            extra_image = image_provider.find_image(extra_image_filename, version=args.version, platform=platform)
            if extra_image:
                break

        if not extra_image:
            logger.error(
                f"Failed to find extra image '{extra_image_filename}' for {hostname} {args.version} {model.get_platform()}")
            return result
        extra_images.append(extra_image)

    try:
        if not dry_run:
            model.save_config()
        if generic_upgrade(hostname, model, image, extra_images, dry_run=dry_run):
            result["status"] = "SUCCESS"
        if not dry_run:
            result["current_software_version"] = model.get_software_version()
            result["current_firmware_version"] = model.get_firmware_version()
        else:
            result["current_software_version"] = image.version
    except Exception as exc:
        logger.exception(f"Upgrade failed: {exc}")
    return result


def version(args, hostname, opts, image_providers, dry_run=False):
    result = {
        "status": "FAILED"
    }
    model = get_model(hostname, opts)
    result["version"] = model.get_software_version()
    result["status"] = "SUCCESS"
    return result


def command(args, hostname, opts, image_providers, dry_run=False):
    result = {
        "status": "FAILED"
    }
    with open(os.path.expanduser(args.commands), 'r') as f:
        commands = f.read().splitlines()

    model = get_model(hostname, opts)

    logger.info(f"Executing commands: {commands}")

    if not dry_run:
        logger.info(model.execute_block(commands))
    else:
        logger.info("DRY RUN")

    result["status"] = "SUCCESS"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action="store_true", default=False)
    parser.add_argument("-K", "--prompt-key-password", help="Prompt ssh key password", default=False, action="store_true")
    parser.add_argument("-P", "--prompt-password", help="Prompt password", default=False, action="store_true")
    parser.add_argument("-S", "--stop-on-error", help="stop on first error", default=False, action="store_true")
    parser.add_argument("-l", "--limit", help="Limit to hosts/groups", default="")
    parser.add_argument("-C", "--check", help="Check mode, don't make changes", default=False, action="store_true")
    parser.add_argument("inventory", help="Inventory file")

    subparsers = parser.add_subparsers(help='actions', required=True)
    update_parser = subparsers.add_parser("update")
    command_parser = subparsers.add_parser("command")
    version_parser = subparsers.add_parser("version")

    update_parser.add_argument("version", help="image version")
    update_parser.set_defaults(func=update)
    command_parser.add_argument("commands", help="File containing commands")
    command_parser.set_defaults(func=command)
    version_parser.set_defaults(func=version)


    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger(None).setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.limit:
        limits = args.limit.split(",")
    else:
        limits = []

    with open(args.inventory, 'r') as f:
        inventory_data = yaml.load(f.read(), Loader=yaml.SafeLoader)
        if "opts" not in inventory_data:
            inventory_data["opts"] = {}
        if args.prompt_key_password:
            inventory_data["opts"]["ssh_key_password"] = getpass.getpass("sshkey password: ")
        if args.prompt_password:
            inventory_data["opts"]["password"] = getpass.getpass("password: ")
        inventory = Inventory.load_from_dict(inventory_data)

    if limits:
        hosts = inventory.filter_hosts(limits)
    else:
        hosts = inventory.hosts

    image_providers = []
    for source_name, source_opts in inventory.sources.items():
        source_type = source_opts.get("type", "local")
        if source_type not in IMAGE_PROVIDERS:
            raise RuntimeError(f"Invalid image source type {source_type} on source {source_name}")
        del source_opts["type"]
        image_providers.append(IMAGE_PROVIDERS[source_type](source_name, **source_opts))

    success = 0
    failed = 0

    results = {}
    for hostname, opts in hosts.items():
        results[hostname] = {
            "status": "SKIPPED",
        }
    for hostname, opts in hosts.items():
        try:
            results[hostname] = args.func(args, hostname, opts, image_providers=image_providers,
                                          dry_run=args.check)
            if results[hostname]["status"] == "SUCCESS":
                success += 1
            else:
                failed += 1
                if args.stop_on_error:
                    break
        except Exception as exc:
            results[hostname] = {"status": "FAILED"}
            logger.exception(f"Failed host {hostname}: {exc}")
            failed += 1
            if args.stop_on_error:
                break

    details = ""
    if args.check:
        details = " DRY RUN"
    print(f"\n\nSummary{details}:")
    if args.func == update:
        print(f"{'status':10s} {'hostname':30s} {'initial_version':20s} -> {'new_version':20s} {'initial_firmware':20s} -> {'new_firmware':20s}")
        for hostname, result in results.items():
            print(
                f"{result['status']:10s} {hostname:30s} {result.get('initial_software_version', 'None'):20s} -> {result.get('current_software_version', 'None'):20s} "
                f"{result.get('initial_firmware_version', 'None'):20s} -> {result.get('current_firmware_version', 'None'):20s}"
            )
    elif args.func == command:
        print(
            f"{'status':10s} {'hostname':30s}")
        for hostname, result in results.items():
            print(
                f"{result['status']:10s} {hostname:30s}"
            )
    elif args.func == version:
        print(
            f"{'status':10s} {'hostname':30s} {'version':30s}")
        for hostname, result in results.items():
            print(
                f"{result['status']:10s} {hostname:30s} {result.get('version', 'None'):20s}"
            )

    if not failed:
        print(f"All done, success: {success}, failed: {failed}")
    else:
        print(f"All done, success: {success}, failed: {failed}")


if __name__ == '__main__':
    main()
