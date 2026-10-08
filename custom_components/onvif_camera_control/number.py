"""Numeric video controls for independently configured ONVIF streams."""

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .display_names import stream_name

_LOGGER = logging.getLogger(__name__)
SETTINGS = {
    "fps": ("Bildefrekvens", "fps", "FrameRateRange"),
    "iframe": ("I-frame-intervall", None, "GovLengthRange"),
    "bitrate": ("Bitrate", "kbit/s", None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    camera_data = hass.data[DOMAIN][entry.entry_id]
    client = camera_data["client"]
    coordinator = camera_data["coordinator"]
    entities = []
    for token, data in coordinator.data.items():
        try:
            options = await client.get_encoder_options(token)
            h264 = getattr(options, "H264", None)
            if h264 is None or str(data.get("encoding")).upper() != "H264":
                continue
            for setting, (_, _, range_name) in SETTINGS.items():
                if setting == "bitrate":
                    limits = await client.refresh_bitrate_limits(token)
                    if limits is None:
                        _LOGGER.info("No safe bitrate range for stream %s (%s)", token, entry.title)
                        continue
                    minimum, maximum = limits
                else:
                    bounds = getattr(h264, range_name, None)
                    if bounds is None:
                        continue
                    minimum, maximum = int(bounds.Min), int(bounds.Max)
                entities.append(OnvifVideoNumber(
                    coordinator, client, entry, token, setting, minimum, maximum
                ))
        except Exception:
            _LOGGER.exception("Unable to load numeric controls for %s", token)
    async_add_entities(entities)


class OnvifVideoNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_native_step = 1

    def __init__(self, coordinator, client, entry, token, setting, minimum, maximum):
        super().__init__(coordinator)
        self.client = client
        self.token = token
        self.setting = setting
        label, unit, _ = SETTINGS[setting]
        self._attr_name = f"{stream_name(coordinator, token)} {label}"
        # Preserve existing HA entity registry entries on upgrade.
        self._attr_unique_id = f"{entry.entry_id}_{token}_{setting}_number"
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_unit_of_measurement = unit
        if setting == "bitrate":
            self._attr_mode = NumberMode.BOX
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ONVIF",
        )

    def _current_limits(self):
        data = (self.coordinator.data or {}).get(self.token)
        if data is None:
            return None
        return self.client.cached_bitrate_limits(
            self.token, data.get("encoding"), (data.get("width"), data.get("height"))
        )

    @property
    def available(self):
        if self.setting == "bitrate" and self._current_limits() is None:
            return False
        return super().available

    @property
    def native_min_value(self):
        if self.setting == "bitrate":
            limits = self._current_limits()
            return limits[0] if limits else self._attr_native_min_value
        return self._attr_native_min_value

    @property
    def native_max_value(self):
        if self.setting == "bitrate":
            limits = self._current_limits()
            return limits[1] if limits else self._attr_native_max_value
        return self._attr_native_max_value

    @property
    def native_value(self):
        data = (self.coordinator.data or {}).get(self.token)
        return data.get(self.setting) if data else None

    async def async_set_native_value(self, value):
        await self.client.update_encoder_setting(self.token, self.setting, int(value))
        await self.coordinator.async_request_refresh()
