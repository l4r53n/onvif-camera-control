"""Config and options flow for a portable per-camera integration."""

import asyncio
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv, selector

from .camera_client import CameraControlClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
CONF_BITRATE_MIN = "bitrate_min_kbps"
CONF_BITRATE_MAX = "bitrate_max_kbps"


class OnvifCameraControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1  # Keep existing config entries and unique IDs unchanged.

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(f"{host.lower()}:{port}")
            self._abort_if_unique_id_configured()
            client = CameraControlClient(host, port, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            try:
                async with asyncio.timeout(15):
                    await client.connect()
            except Exception:
                _LOGGER.debug("Could not connect to ONVIF camera", exc_info=True)
                errors["base"] = "cannot_connect"
            finally:
                await client.close()
            if not errors:
                return self.async_create_entry(
                    title=f"ONVIF Camera ({host})",
                    data={CONF_HOST: host, CONF_PORT: port,
                          CONF_USERNAME: user_input[CONF_USERNAME],
                          CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT, default=80): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Required(CONF_USERNAME, default="admin"): cv.string,
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return OnvifOptionsFlow(config_entry)


class OnvifOptionsFlow(config_entries.OptionsFlow):
    """Manual fallback when Media2 offers no trustworthy bitrate limits."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            minimum = user_input[CONF_BITRATE_MIN]
            maximum = user_input[CONF_BITRATE_MAX]
            if (minimum == 0) != (maximum == 0) or (minimum and minimum > maximum):
                errors["base"] = "invalid_bitrate_range"
            else:
                return self.async_create_entry(title="", data={
                    CONF_BITRATE_MIN: minimum, CONF_BITRATE_MAX: maximum,
                })
        options = self._entry.options
        return self.async_show_form(step_id="init", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_BITRATE_MIN, default=options.get(CONF_BITRATE_MIN, 0)):
                vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
            vol.Required(CONF_BITRATE_MAX, default=options.get(CONF_BITRATE_MAX, 0)):
                vol.All(vol.Coerce(int), vol.Range(min=0, max=1_000_000)),
        }))
