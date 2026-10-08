"""Offline regression tests: no live cameras or Home Assistant installation needed."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "onvif_camera_control"


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def install_stubs():
    # No production dependencies are required for the pure-logic tests.
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    ha.__path__ = []
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    helpers.__path__ = []
    aio = sys.modules.setdefault("homeassistant.helpers.aiohttp_client", types.ModuleType("homeassistant.helpers.aiohttp_client"))
    aio.async_get_clientsession = lambda hass: None
    onvif = sys.modules.setdefault("onvif", types.ModuleType("onvif"))
    onvif.ONVIFCamera = object
    package = sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
    package.__path__ = [str(ROOT / "custom_components")]
    sub = sys.modules.setdefault("custom_components.onvif_camera_control", types.ModuleType("custom_components.onvif_camera_control"))
    sub.__path__ = [str(COMP)]


install_stubs()
media = load_file(COMP / "media2_client.py", "custom_components.onvif_camera_control.media2_client")
validation = load_file(COMP / "validation.py", "custom_components.onvif_camera_control.validation")
client_module = load_file(COMP / "camera_client.py", "custom_components.onvif_camera_control.camera_client")
generator = load_file(ROOT / "tools" / "generate_dashboard.py", "dashboard_generator")


def xml_options(*options):
    return ('''<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
      xmlns:t="http://www.onvif.org/ver20/media/wsdl"
      xmlns:a="http://www.onvif.org/ver10/schema"><s:Body>
      <t:GetVideoEncoderConfigurationOptionsResponse>'''+ "".join(options) + '''
      </t:GetVideoEncoderConfigurationOptionsResponse></s:Body></s:Envelope>''').encode()


def option(codec="H264", minimum=64, maximum=2048, sizes=((2880, 1624),)):
    dims = "".join(f"<a:ResolutionsAvailable><a:Width>{w}</a:Width><a:Height>{h}</a:Height></a:ResolutionsAvailable>" for w, h in sizes)
    return (f"<t:Options><a:Encoding>{codec}</a:Encoding>{dims}"
            f"<a:BitrateRange><a:Min>{minimum}</a:Min><a:Max>{maximum}</a:Max></a:BitrateRange></t:Options>")


def test_matching_encoding_resolution():
    blob = xml_options(option(), option(codec="H265", minimum=128, maximum=8000))
    assert media.parse_bitrate_options(blob, "H264", (2880, 1624)) == (64, 2048)
    assert media.parse_bitrate_options(blob, "H264", (640, 360)) is None
    assert media.parse_bitrate_options(blob, "H265", (2880, 1624)) == (128, 8000)


def test_conflicting_ranges_are_rejected():
    blob = xml_options(option(minimum=64, maximum=2048), option(minimum=128, maximum=4096))
    assert media.parse_bitrate_options(blob, "H264", (2880, 1624)) is None


def test_invalid_ranges_and_missing_options():
    assert media.parse_bitrate_options(xml_options(option(minimum=2048, maximum=64)), "H264", (2880,1624)) is None
    assert media.parse_bitrate_options(xml_options(), "H264", (2880,1624)) is None


def test_soap_fault_and_dtd_rejected():
    import pytest
    with pytest.raises(ValueError):
        media.parse_bitrate_options(b'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><s:Fault/></s:Body></s:Envelope>', "H264", (1, 1))
    with pytest.raises(ValueError):
        media.parse_bitrate_options(b'<!DOCTYPE x><root/>', "H264", (1, 1))
    with pytest.raises(ValueError):
        media.parse_bitrate_options(b'0' * (1024 * 1024 + 1), "H264", (1, 1))


def test_endpoint_restrictions():
    import pytest
    assert media.validate_service_url("10.0.0.110", "http://10.0.0.110/onvif/media2_service")
    for url in ("http://127.0.0.1/media", "http://192.168.1.1/media", "file:///etc/passwd",
                "http://user:pw@10.0.0.110/", "http://10.0.0.110/#fragment"):
        with pytest.raises(ValueError):
            media.validate_service_url("10.0.0.110", url)


def test_wsse_digest_never_embeds_password():
    xml = media._soap("VEToken_1", "admin", "secret-password").decode()
    assert "secret-password" not in xml
    assert "PasswordDigest" in xml
    assert "VEToken_1" in xml


def test_stream_specific_cache_and_safe_write():
    from types import SimpleNamespace as N
    async def run():
        client = client_module.CameraControlClient("192.168.1.33", 80, "a", "b", bitrate_override=(64, 2048))
        config = N(Encoding="H264", Resolution=N(Width=1920, Height=1080),
                   RateControl=N(FrameRateLimit=20, BitrateLimit=512), H264=N(GovLength=15))
        options = N(H264=N(FrameRateRange=N(Min=1, Max=25), GovLengthRange=N(Min=1, Max=100)))
        client.get_encoder_configuration = lambda token: asyncio.sleep(0, result=config)
        client.get_encoder_options = lambda token: asyncio.sleep(0, result=options)
        client.set_encoder_configuration = lambda cfg: asyncio.sleep(0)
        assert await client.refresh_bitrate_limits("tok", config) == (64, 2048)
        await client.update_encoder_setting("tok", "bitrate", 1024)
        assert config.RateControl.BitrateLimit == 1024
        try:
            await client.update_encoder_setting("tok", "bitrate", 4096)
            assert False, "Unvalidated bitrate write accepted"
        except ValueError:
            pass
        config.Resolution.Width = 1280
        assert client.cached_bitrate_limits("tok", "H264", (1280, 1080)) is None
        try:
            await client.update_encoder_setting("tok", "bitrate", 512)
            assert False, "Stale limits accepted"
        except ValueError:
            pass
    asyncio.run(run())


def test_dashboard_for_two_cameras_preserves_real_entity_ids():
    id_a, id_b = "config_a", "config_b"
    registry = {"data": {"entities": [
        {"platform": "onvif_camera_control", "config_entry_id": entry, "unique_id": f"{entry}_{token}_{suffix}", "entity_id": f"{kind}.some_{entry}_{token}_{setting}"}
        for entry in (id_a, id_b)
        for token in ("VEToken_1", "VEToken_2")
        for setting, suffix, kind in (("resolution", "resolution_select", "select"), ("fps", "fps_number", "number"), ("bitrate", "bitrate_number", "number"), ("iframe", "iframe_number", "number"))
    ]}}
    found = generator.collect(registry)
    assert len(found) == 2
    dashboard = generator.generate(found, {id_a: "camera.salongen"}, {id_a: "Salong", id_b: "Cockpit"})
    assert len(dashboard["views"]) == 3
    assert dashboard["views"][1]["sections"][0]["cards"][1]["entity"] == "camera.salongen"
    blob = "\n".join(generator.to_yaml(dashboard))
    import yaml
    assert yaml.safe_load(blob)["views"][2]["title"] == "Cockpit"
    assert "number.some_config_b_VEToken_2_bitrate" in blob
    assert "192.168." not in blob


def test_unique_id_format_unchanged():
    from pathlib import Path
    assert 'f"{entry.entry_id}_{token}_{setting}_number"' in (COMP / "number.py").read_text()
    assert 'f"{entry.entry_id}_{token}_resolution_select"' in (COMP / "select.py").read_text()
