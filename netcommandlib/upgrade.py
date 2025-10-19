import logging
from typing import List

from models.model import Model
from netcommandlib.version import compare_version
from netcommandlib import image

logger = logging.getLogger("generic_updater")


def generic_upgrade(
        hostname: str,
        model: Model,
        image: image.GenericImage,
        extra_images: List[image.GenericImage],
        dry_run=False
):

    current_version = model.get_software_version()
    current_firmware = model.get_firmware_version()

    if image.platform != model.get_platform():
        logger.error(
            f"Skipping upgrade, device platform '{model.get_platform()}' don't match image platform '{image.platform}'"
        )
        return False

    if compare_version(image.version, current_version) < 0:
        # Current version is bigger than given version
        logger.warning(
            f"Skipping upgrade, current version '{current_version}' is bigger than update version '{image.version}'"
        )
        return False
    if compare_version(image.version, current_version) < 1:
        # Current version is same as given version
        logger.warning(
            f"Skipping upgrade, current version '{current_version}' is same as update version '{image.version}'"
        )
        return True

    for extra_image in extra_images:
        if extra_image.platform != model.get_platform():
            logger.error(
                f"Skipping upgrade, device platform '{model.get_platform()}' "
                f"don't match image platform '{extra_image.platform}'"
            )
            return False

        if compare_version(extra_image.version, current_version) < 0:
            # Current version is bigger than given version
            logger.warning(
                f"Skipping upgrade, current version '{current_version}' "
                f"is bigger than update version '{extra_image.version}'"
            )
            return False
        if compare_version(extra_image.version, current_version) < 1:
            # Current version is same as given version
            logger.warning(
                f"Skipping upgrade, current version '{current_version}' "
                f"is same as update version '{extra_image.version}'"
            )
            return True

    logger.info(f"{hostname}: Upgrading from '{current_version}' to '{image.version}'")

    if dry_run:
        logger.info(f"{hostname}: Dry run, not executing upgrade commands")

    model.save_config(dry_run=dry_run)

    result = model.upgrade(image, extra_images, dry_run=dry_run)

    if not result:
        logger.error(f"{hostname}: Upgrade command failed!")
        return False

    updated_version = model.get_software_version()
    updated_firmware = model.get_firmware_version()

    if dry_run:
        logger.info(f"{hostname}: Updated successfully from version '{current_version}' (fw: {current_firmware}) "
                    f"to version '{image.version}' (fw: ???) DRY RUN")
        return True

    if compare_version(updated_version, image.version) == 0:
        logger.info(f"{hostname}: Updated successfully from version '{current_version}' (fw: {current_firmware}) "
                    f"to version '{updated_version}' (fw: {updated_firmware})")

        return True
    elif compare_version(current_version, updated_version) < 0:
        logger.error(
            f"{hostname}: Update failed, version '{updated_version}' "
            f"don't match expected version '{image.version}' after upgrade"
        )
    elif current_version == updated_version:
        logger.error(f"{hostname}: Update failed, versio is '{updated_version}' after update (same as original)")
    else:
        logger.error(
            f"{hostname}: Update failed, version '{updated_version}' "
            f"don't match expected version '{image.version}' after upgrade"
        )
    return False
