"""Resolution controls for ONVIF cameras."""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .display_names import stream_name

_LOGGER = logging.getLogger(__name__)


# Known camera formats get meaningful names; unknown formats show dimensions.
_RESOLUTION_NAMES = {
    (2880, 1624): "5 MP",
    (2560, 1440): "4 MP",
    (2304, 1296): "3 MP",
    (1920, 1080): "1080p",
    (1280, 720): "720p",
    (704, 576): "4CIF",
    (640, 360): "360p",
    (352, 288): "CIF",
}


def resolution_label(width: int, height: int) -> str:
    """Return friendly label without changing ONVIF resolution values."""
    dimensions = f"{width} × {height}"
    label = _RESOLUTION_NAMES.get((width, height))
    return f"{label} ({dimensions})" if label else dimensions


async def async_setup_entry(hass, entry, async_add_entities):
    """Create resolution controls for discovered encoders."""
    camera_data = hass.data[DOMAIN][entry.entry_id]
    client = camera_data["client"]
    coordinator = camera_data["coordinator"]

    entities = []

    for token in coordinator.data:
        try:
            options = await client.get_encoder_options(token)
            h264 = getattr(options, "H264", None)

            if h264 is None:
                continue

            resolutions = [
                (int(r.Width), int(r.Height))
                for r in h264.ResolutionsAvailable or []
            ]

            if resolutions:
                entities.append(
                    OnvifResolutionSelect(
                        coordinator, client, entry,
                        token, resolutions
                    )
                )

        except Exception:
            _LOGGER.exception(
                "Unable to load resolution options for %s",
                token,
            )

    async_add_entities(entities)


class OnvifResolutionSelect(CoordinatorEntity, SelectEntity):
    """Select video encoder resolution."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator, client, entry, token, resolutions
    ):
        super().__init__(coordinator)

        self.client = client
        self.token = token

        self._attr_name = f"{token} Oppløsning"
        self._attr_name = self._attr_name.replace(
            str(token), stream_name(coordinator, token), 1
        )
        self._attr_unique_id = (
            f"{entry.entry_id}_{token}_resolution_select"
        )
        self._resolution_map = {
            resolution_label(width, height): (width, height)
            for width, height in resolutions
        }
        self._attr_options = list(self._resolution_map)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ONVIF",
        )

    @property
    def current_option(self):
        """Return the active resolution."""
        data = (self.coordinator.data or {}).get(self.token)

        if data is None:
            return None

        return resolution_label(int(data["width"]), int(data["height"]))

    async def async_select_option(self, option):
        """Change the camera resolution."""
        if option not in self.options:
            raise ValueError("Unsupported resolution")

        width, height = self._resolution_map[option]

        await self.client.update_encoder_setting(
            self.token,
            "resolution",
            (width, height),
        )

        await self.coordinator.async_request_refresh()
