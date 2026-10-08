"""Data coordinator for ONVIF Camera Control."""

import asyncio
import logging

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=60)


class OnvifCameraCoordinator(DataUpdateCoordinator):
    """Coordinate video settings for one ONVIF camera."""

    def __init__(self, hass: HomeAssistant, client, camera_name: str):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"ONVIF Camera Control {camera_name}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.stream_names = {}

    async def _async_update_data(self):
        """Read current video encoder configurations."""
        try:
            async with asyncio.timeout(15):
                configurations = (
                    await self.client.get_encoder_configurations()
                )

            result = {}

            for config in configurations or []:
                token = getattr(config, "token", None)
                resolution = getattr(config, "Resolution", None)
                if not token or resolution is None:
                    continue
                rate = getattr(config, "RateControl", None)
                h264 = getattr(config, "H264", None)

                result[token] = {
                    "token": token,
                    "name": config.Name,
                    "encoding": config.Encoding,
                    "width": config.Resolution.Width,
                    "height": config.Resolution.Height,
                    "fps": getattr(rate, "FrameRateLimit", None),
                    "bitrate": getattr(rate, "BitrateLimit", None),
                    "iframe": (
                        h264.GovLength
                        if h264 is not None
                        else None
                    ),
                    "profile": (
                        h264.H264Profile
                        if h264 is not None
                        else None
                    ),
                }

            if not self.stream_names:
                def size(key):
                    record = result[key]
                    return int(record["width"]) * int(record["height"])
                tokens = sorted(result, key=lambda key: (-size(key), str(key)))
                for idx, key in enumerate(tokens, 1):
                    self.stream_names[key] = (
                        "Hovedstrøm" if idx == 1 else
                        "Sekundærstrøm" if idx == 2 else f"Videostrøm {idx}"
                    )
            return result

        except Exception as err:
            raise UpdateFailed(
                f"Unable to read camera settings: "
                f"{err.__class__.__name__}"
            ) from err
