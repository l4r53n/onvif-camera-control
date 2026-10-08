"""Read bitrate capabilities from ONVIF Media2, without changing the camera.

Only create a bitrate control when the response is unambiguous for the requested
codec and video resolution. Media2 does not need to share Media1 tokens: a
rejected token falls back to *generic* device capability discovery.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import os
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from homeassistant.helpers.aiohttp_client import async_get_clientsession

MEDIA2_NS = "http://www.onvif.org/ver20/media/wsdl"
SCHEMA_NS = "http://www.onvif.org/ver10/schema"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"


def _tag(name):
    return f"{{{SCHEMA_NS}}}{name}"


def _limits(range_element):
    """Return the ONVIF tt:IntRange or None when invalid."""
    if range_element is None:
        return None
    try:
        minimum = int(range_element.findtext(_tag("Min")))
        maximum = int(range_element.findtext(_tag("Max")))
    except (TypeError, ValueError):
        return None
    if minimum < 1 or maximum < minimum or maximum > 1_000_000:
        return None
    return (minimum, maximum)


def parse_bitrate_options(payload: bytes, encoding: str, resolution: tuple[int, int]):
    """Read an unambiguous bitrate range from a Media2 SOAP reply.

    Supports differing XML namespace prefixes and rejects conflicting ranges.
    This never uses a range intended for another codec or resolution.
    """
    if len(payload) > 1024 * 1024:
        raise ValueError("Oversized Media2 response")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD is not permitted in ONVIF response")
    root = ET.fromstring(payload)
    fault = root.find(f".//{{{SOAP_NS}}}Fault")
    if fault is not None:
        raise ValueError("ONVIF Media2 returned a SOAP fault")
    ranges = set()
    for option in root.findall(f".//{{{MEDIA2_NS}}}Options"):
        codec = option.findtext(_tag("Encoding"))
        if not codec or codec.upper().split("/")[-1] != encoding.upper().split("/")[-1]:
            continue
        sizes = set()
        for item in option.findall(_tag("ResolutionsAvailable")):
            try:
                sizes.add((int(item.findtext(_tag("Width"))), int(item.findtext(_tag("Height")))))
            except (TypeError, ValueError):
                continue
        if sizes and resolution not in sizes:
            continue
        limits = _limits(option.find(_tag("BitrateRange")))
        if limits:
            ranges.add(limits)
    if len(ranges) == 1:
        return ranges.pop()
    return None


def _wsse_header(username: str, password: str):
    """Construct the standard WS-Security UsernameToken PasswordDigest."""
    import xml.sax.saxutils as sax

    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    nonce = os.urandom(16)
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
    nonce_b64 = base64.b64encode(nonce).decode()
    user = sax.escape(username)
    return (
        f'<wsse:Security xmlns:wsse="{WSSE_NS}" xmlns:wsu="{WSU_NS}" '
        's:mustUnderstand="1"><wsse:UsernameToken>'
        f'<wsse:Username>{user}</wsse:Username>'
        f'<wsse:Password Type="{WSSE_NS}#PasswordDigest">{digest}</wsse:Password>'
        f'<wsse:Nonce EncodingType="{WSSE_NS}#Base64Binary">{nonce_b64}</wsse:Nonce>'
        f'<wsu:Created>{created}</wsu:Created>'
        '</wsse:UsernameToken></wsse:Security>'
    )


def _soap(token: str | None, username: str | None, password: str | None):
    import xml.sax.saxutils as sax

    header = _wsse_header(username, password) if username and password else ""
    token_xml = f"<tr2:ConfigurationToken>{sax.escape(token)}</tr2:ConfigurationToken>" if token else ""
    return (
        f'<s:Envelope xmlns:s="{SOAP_NS}" xmlns:tr2="{MEDIA2_NS}">'
        f'<s:Header>{header}</s:Header><s:Body>'
        f'<tr2:GetVideoEncoderConfigurationOptions>{token_xml}'
        '</tr2:GetVideoEncoderConfigurationOptions></s:Body></s:Envelope>'
    ).encode()


def validate_service_url(host: str, url: str):
    """Limit discovery to the camera host, never arbitrary advertised URLs."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Invalid Media2 URL scheme or hostname")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Media2 URL must not contain credentials or fragments")
    try:
        port = parsed.port
    except ValueError as err:
        raise ValueError("Invalid Media2 URL port") from err
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid Media2 URL port")
    expected = host.strip("[]").lower().rstrip(".")
    actual = parsed.hostname.lower().rstrip(".")
    if actual != expected:
        raise ValueError("Media2 endpoint points at a different camera host")
    try:
        ip = ipaddress.ip_address(actual)
    except ValueError:
        if actual in ("localhost",) or "." not in actual:
            raise ValueError("Use the camera's local hostname or IP") from None
    else:
        if not ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_link_local:
            raise ValueError("Media2 requires a private camera address")
    return url


class Media2Client:
    """Read media capabilities from the selected camera."""

    def __init__(self, hass, host, url, username=None, password=None):
        self.hass = hass
        self.url = validate_service_url(host, url)
        self.username = username
        self.password = password

    async def _query(self, token, authenticated):
        session = async_get_clientsession(self.hass)
        payload = _soap(token, self.username if authenticated else None, self.password if authenticated else None)
        async with asyncio.timeout(6):
            async with session.post(
                self.url,
                data=payload,
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                allow_redirects=False,
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    raise ValueError("ONVIF endpoint attempted a redirect")
                if response.status in (401, 403):
                    raise PermissionError("Media2 authentication required")
                response.raise_for_status()
                if response.content_length and response.content_length > 1024 * 1024:
                    raise ValueError("Oversized Media2 response")
                return await response.content.read(1024 * 1024 + 1)

    async def get_bitrate_limits(self, token, encoding, resolution):
        """Find one range for this codec/resolution, preferably token-scoped."""
        # Anonymous first, then WS-Security for cameras requiring a login.
        for query_token in (token, None):
            for authenticated in (False, True) if self.username and self.password else (False,):
                try:
                    payload = await self._query(query_token, authenticated)
                    limits = parse_bitrate_options(payload, encoding, resolution)
                    if limits is not None:
                        return limits
                    # No matching range may mean token unsupported; try generic.
                    break
                except Exception:
                    # Media2 is optional: try authenticated and generic requests.
                    # Timeouts and unsupported tokens must never break Media1.
                    continue
        return None
