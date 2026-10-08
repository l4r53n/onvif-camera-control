"""ONVIF Media1 camera configuration with optional Media2 capability discovery."""

from __future__ import annotations

import asyncio
import logging

from onvif import ONVIFCamera

from .media2_client import MEDIA2_NS, Media2Client
from .validation import validate_encoder_setting

_LOGGER = logging.getLogger(__name__)


class CameraControlClient:
    """One isolated, writable ONVIF camera. All writes are serialized."""

    def __init__(self, host, port, username, password, hass=None, bitrate_override=None):
        self.host = host
        self.port = int(port)
        self._username = username
        self._password = password
        self.hass = hass
        self.bitrate_override = bitrate_override
        self._camera = None
        self._media = None
        self._write_lock = asyncio.Lock()
        self._bitrate_limits = {}
        self.profile_names = {}

    async def connect(self):
        """Connect to Media1, discovering any Media2 endpoint."""
        await self.close()
        camera = ONVIFCamera(self.host, self.port, self._username, self._password)
        try:
            await camera.update_xaddrs()
            media = await camera.create_media_service()
            profiles = await media.GetProfiles()
        except Exception:
            await camera.close()
            raise
        self._camera = camera
        self._media = media
        for profile in profiles or []:
            encoder = getattr(profile, "VideoEncoderConfiguration", None)
            token = getattr(encoder, "token", None)
            name = getattr(profile, "Name", None)
            if token and name and token not in self.profile_names:
                self.profile_names[str(token)] = str(name)

    async def get_profiles(self):
        return await self._media.GetProfiles()

    async def get_encoder_configurations(self):
        return await self._media.GetVideoEncoderConfigurations()

    async def get_encoder_options(self, token):
        return await self._media.GetVideoEncoderConfigurationOptions({"ConfigurationToken": token})

    async def get_encoder_configuration(self, token):
        return await self._media.GetVideoEncoderConfiguration({"ConfigurationToken": token})

    async def close(self):
        camera = self._camera
        self._camera = None
        self._media = None
        self._bitrate_limits.clear()
        self.profile_names.clear()
        if camera is not None:
            await camera.close()

    @property
    def media2_url(self):
        return (self._camera.xaddrs or {}).get(MEDIA2_NS) if self._camera else None

    def cached_bitrate_limits(self, token, encoding=None, resolution=None):
        """Only return limits if they describe the *current* stream format."""
        item = self._bitrate_limits.get(str(token))
        if item is None:
            return None
        fmt, size, limits = item
        if encoding is not None and fmt != str(encoding):
            return None
        if resolution is not None and size != tuple(resolution):
            return None
        return limits

    async def refresh_bitrate_limits(self, token, configuration=None):
        """Obtain limits without writing; None means no safe writable control."""
        token = str(token)
        self._bitrate_limits.pop(token, None)
        configuration = configuration or await self.get_encoder_configuration(token)
        encoding = str(configuration.Encoding)
        resolution = (int(configuration.Resolution.Width), int(configuration.Resolution.Height))
        if encoding.upper() != "H264" or getattr(configuration, "RateControl", None) is None:
            return None
        limits = self.bitrate_override
        if limits is None and self.hass is not None and self.media2_url:
            try:
                media2 = Media2Client(
                    self.hass, self.host, self.media2_url, self._username, self._password
                )
                limits = await media2.get_bitrate_limits(token, encoding, resolution)
            except Exception as err:
                _LOGGER.debug("Media2 bitrate discovery unavailable for %s: %s", self.host, type(err).__name__)
        if limits is not None:
            self._bitrate_limits[token] = (encoding, resolution, limits)
        return limits

    async def set_encoder_configuration(self, configuration):
        if self._media is None:
            raise RuntimeError("ONVIF Media service is not connected")
        request = self._media.create_type("SetVideoEncoderConfiguration")
        request.Configuration = configuration
        request.ForcePersistence = True
        await self._media.SetVideoEncoderConfiguration(request)

    async def update_encoder_setting(self, token, setting, value):
        """Validate, write and verify, then refresh limits if resolution changed."""
        async with self._write_lock:
            updated = await self._update_encoder_setting_locked(token, setting, value)
        if setting == "resolution":
            try:
                await self.refresh_bitrate_limits(token, updated)
            except Exception:
                _LOGGER.debug("Could not refresh bitrate limits after resolution change")
        return updated

    async def _update_encoder_setting_locked(self, token, setting, value):
        configuration = await self.get_encoder_configuration(token)
        options = await self.get_encoder_options(token)
        if setting == "bitrate":
            limits = self.cached_bitrate_limits(
                token,
                str(configuration.Encoding),
                (int(configuration.Resolution.Width), int(configuration.Resolution.Height)),
            )
            if limits is None:
                raise ValueError("Bitrate limits are unavailable or stale for this stream")
            if not isinstance(value, int) or isinstance(value, bool) or not limits[0] <= value <= limits[1]:
                raise ValueError(f"Bitrate must be an integer between {limits[0]} and {limits[1]}")
            if getattr(configuration, "RateControl", None) is None:
                raise ValueError("Camera does not expose bitrate rate control")
        else:
            validate_encoder_setting(options, setting, value)

        if setting == "resolution":
            configuration.Resolution.Width = int(value[0])
            configuration.Resolution.Height = int(value[1])
        elif setting == "fps":
            configuration.RateControl.FrameRateLimit = int(value)
        elif setting == "iframe":
            configuration.H264.GovLength = int(value)
        elif setting == "bitrate":
            configuration.RateControl.BitrateLimit = int(value)
        else:
            raise ValueError(f"Unsupported setting: {setting}")

        await self.set_encoder_configuration(configuration)
        updated = await self.get_encoder_configuration(token)
        if setting == "resolution":
            actual = (int(updated.Resolution.Width), int(updated.Resolution.Height))
            expected = tuple(value)
        elif setting == "fps":
            actual = int(updated.RateControl.FrameRateLimit)
            expected = int(value)
        elif setting == "bitrate":
            actual = int(updated.RateControl.BitrateLimit)
            expected = int(value)
        else:
            actual = int(updated.H264.GovLength)
            expected = int(value)
        if actual != expected:
            raise RuntimeError(f"Camera did not apply {setting}: expected {expected}, got {actual}")
        return updated
