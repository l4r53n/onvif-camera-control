"""ONVIF Camera Control integration."""

import asyncio
import logging


from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .camera_client import CameraControlClient
from .coordinator import OnvifCameraCoordinator
from .const import DOMAIN
from .config_flow import CONF_BITRATE_MIN, CONF_BITRATE_MAX

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER]


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    """Initialize ONVIF Camera Control."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up an individual ONVIF camera."""

    lower = entry.options.get(CONF_BITRATE_MIN, 0)
    upper = entry.options.get(CONF_BITRATE_MAX, 0)
    override = (int(lower), int(upper)) if lower and upper else None

    client = CameraControlClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        hass=hass,
        bitrate_override=override,
    )

    try:
        async with asyncio.timeout(20):
            await client.connect()

            coordinator = OnvifCameraCoordinator(
                hass,
                client,
                entry.title,
            )

            await coordinator.async_config_entry_first_refresh()

    except Exception as err:
        await client.close()
        _LOGGER.warning(
            "Unable to initialize ONVIF camera %s: %s",
            entry.data[CONF_HOST],
            err.__class__.__name__,
        )
        raise ConfigEntryNotReady(
            f"ONVIF camera initialization failed: "
            f"{err.__class__.__name__}"
        ) from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    try:
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORMS
        )
    except Exception:
        _LOGGER.exception(
            "Unable to load sensor platform for %s",
            entry.data[CONF_HOST],
        )
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await coordinator.async_shutdown()
        await client.close()
        raise

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info(
        "ONVIF Camera Control initialized for %s",
        entry.data[CONF_HOST],
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload an individual ONVIF camera."""

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    if not unloaded:
        return False

    camera_data = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )

    if camera_data is not None:
        coordinator = camera_data["coordinator"]
        await coordinator.async_shutdown()
        await camera_data["client"].close()

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a single camera when its bitrate fallback options change."""
    await hass.config_entries.async_reload(entry.entry_id)
