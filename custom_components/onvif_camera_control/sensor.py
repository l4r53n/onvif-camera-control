"""Sensors for ONVIF camera video configuration."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .display_names import stream_name


SENSOR_TYPES = {
    "resolution": ("Oppløsning", None),
    "fps": ("Bildefrekvens", "fps"),
    "bitrate": ("Bitrate", "kbit/s"),
    "iframe": ("I-frame-intervall", None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Create sensors for all discovered video encoders."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        OnvifVideoSensor(coordinator, entry, token, sensor_type)
        for token in coordinator.data
        for sensor_type in SENSOR_TYPES
    ]

    async_add_entities(entities)


class OnvifVideoSensor(CoordinatorEntity, SensorEntity):
    """Represent one video encoder setting."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, token, sensor_type):
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._token = token
        self._sensor_type = sensor_type

        label, unit = SENSOR_TYPES[sensor_type]

        self._attr_unique_id = (
            f"{entry.entry_id}_{token}_{sensor_type}"
        )
        self._attr_name = f"{token} {label}"
        self._attr_name = self._attr_name.replace(
            str(token), stream_name(coordinator, token), 1
        )
        self._attr_native_unit_of_measurement = unit

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ONVIF",
        )

    @property
    def native_value(self):
        """Return the current encoder setting."""
        data = (self.coordinator.data or {}).get(self._token)

        if data is None:
            return None

        if self._sensor_type == "resolution":
            return f"{data['width']} × {data['height']}"

        return data.get(self._sensor_type)
