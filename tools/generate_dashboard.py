#!/usr/bin/env python3
"""Generate a portable ONVIF Camera Control dashboard from HA's entity registry.

Reads entity registry only; never reads configuration-entry passwords or modifies
Home Assistant's .storage files. Run again after registering a new camera.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

DOMAIN = "onvif_camera_control"
# Current component's unchanged unique_id suffixes.
SUFFIXES = {
    "_resolution_select": "resolution",
    "_fps_number": "fps",
    "_iframe_number": "iframe",
    "_bitrate_number": "bitrate",
}


def collect(registry):
    """Return {config_entry_id: {token: {setting: entity_id}}}."""
    found = {}
    for row in registry.get("data", {}).get("entities", []):
        if row.get("platform") != DOMAIN or row.get("disabled_by") or row.get("hidden_by"):
            continue
        entry_id, unique_id, entity_id = row.get("config_entry_id"), row.get("unique_id"), row.get("entity_id")
        if not all(isinstance(item, str) and item for item in (entry_id, unique_id, entity_id)):
            continue
        prefix = entry_id + "_"
        if not unique_id.startswith(prefix):
            continue
        remainder = unique_id[len(prefix):]
        for suffix, setting in SUFFIXES.items():
            if remainder.endswith(suffix):
                token = remainder[:-len(suffix)]
                if not token:
                    break
                found.setdefault(entry_id, {}).setdefault(token, {})[setting] = entity_id
                break
    return found


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "kamera"


def tile(entity, name, icon, columns, feature=None):
    result = {
        "type": "tile", "entity": entity, "name": name, "icon": icon,
        "grid_options": {"columns": columns},
    }
    if feature:
        result["features_position"] = "bottom"
        result["features"] = [feature]
    return result


def heading(name, icon):
    return {"type": "heading", "heading": name, "heading_style": "title", "icon": icon}


def stream_section(token, settings, index):
    label = ("Hovedstrøm" if index == 1 else
             "Sekundærstrøm" if index == 2 else f"Videostrøm {index}")
    section = [heading(label, "mdi:video-high-definition" if index == 1 else "mdi:video")]
    if entity := settings.get("resolution"):
        section.append(tile(entity, "Oppløsning", "mdi:aspect-ratio", 12, {"type": "select-options"}))
    if entity := settings.get("fps"):
        section.append(tile(entity, "Bildefrekvens", "mdi:filmstrip", 6,
                            {"type": "numeric-input", "style": "slider"}))
    if entity := settings.get("iframe"):
        section.append(tile(entity, "I-frame-intervall", "mdi:video-outline", 6,
                            {"type": "numeric-input", "style": "buttons"}))
    if entity := settings.get("bitrate"):
        section.append({
            "type": "entities", "show_header_toggle": False,
            "grid_options": {"columns": 12},
            "entities": [{"entity": entity, "name": "Bitrate", "icon": "mdi:speedometer"}],
        })
    return {"type": "grid", "cards": section}


def generate(data, camera_map=None, names=None, presets=None, dashboard_url="/onvif-kontroll"):
    """Build a dashboard with one tab per camera and an overview tab."""
    camera_map = camera_map or {}
    names = names or {}
    presets = presets or {}
    views = []
    overview = [heading("ONVIF-kameraer", "mdi:cctv")]
    for i, (entry_id, streams) in enumerate(sorted(data.items()), 1):
        label = names.get(entry_id) or f"Kamera {i}"
        view_path = f"kamera-{i}-{slug(entry_id[-6:])}"
        preview = camera_map.get(entry_id)
        overview.append({
            "type": "tile", "entity": preview or next(iter(next(iter(streams.values())).values())),
            "name": label,
            "icon": "mdi:cctv", "grid_options": {"columns": 6},
            "tap_action": {"action": "navigate", "navigation_path": f"{dashboard_url}/{view_path}"},
        })
        sections = []
        if preview:
            sections.append({"type": "grid", "column_span": 2, "cards": [
                heading("Direkte kamerabilde", "mdi:cctv"),
                {"type": "picture-entity", "entity": preview, "camera_view": "live",
                 "show_name": False, "show_state": False,
                 "grid_options": {"columns": "full", "rows": "auto"}},
            ]})
        if preset_group := presets.get(entry_id):
            items = [heading("Kameraprofiler", "mdi:tune-variant")]
            for preset in preset_group:
                items.append({
                    "type": "button", "name": preset[0], "icon": "mdi:tune-variant",
                    "grid_options": {"columns": 6},
                    "tap_action": {"action": "perform-action", "perform_action": preset[1],
                                   "confirmation": {"text": f"Bruke profilen {preset[0]}?"}},
                })
            sections.append({"type": "grid", "column_span": 2, "cards": items})
        for j, (token, settings) in enumerate(sorted(streams.items()), 1):
            sections.append(stream_section(token, settings, j))
        views.append({"title": label, "path": view_path,
                      "icon": "mdi:cctv", "type": "sections", "max_columns": 2,
                      "sections": sections})
    return {"title": "ONVIF Kamerakontroll", "views": [
        {"title": "Oversikt", "path": "oversikt", "icon": "mdi:view-dashboard",
         "type": "sections", "max_columns": 2,
         "sections": [{"type": "grid", "column_span": 2, "cards": overview}]},
        *views,
    ]}


def _scalar(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def to_yaml(value, indent=0):
    """Small dependency-free YAML writer (quotes all user-sourced strings)."""
    lines = []
    pad = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            prefix = f"{pad}{key}:"
            if isinstance(item, (list, dict)):
                lines.append(prefix)
                lines.extend(to_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix} {_scalar(item)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (list, dict)):
                lines.append(f"{pad}-")
                lines.extend(to_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    return lines


def _mapping(items, what, value_validator):
    result = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"{what} needs ENTRY_ID=value: {item}")
        entry, value = item.split("=", 1)
        if not entry or not value_validator(value):
            raise ValueError(f"Invalid {what}: {item}")
        result[entry] = value
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", default="/config/.storage/core.entity_registry")
    p.add_argument("--output", default="/config/onvif_kontrollpanel.yaml")
    p.add_argument("--camera", action="append", default=[], metavar="ENTRY_ID=camera.entity_id")
    p.add_argument("--name", action="append", default=[], metavar="ENTRY_ID=Visningsnavn")
    p.add_argument("--preset", action="append", default=[], metavar="ENTRY_ID=Etikett:script.entity_id")
    p.add_argument("--dashboard-url", default="/onvif-kontroll",
                   help="Må stemme med URL-en til Lovelace-dashboardet")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args(argv)
    registry_path = Path(args.registry)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = collect(registry)
    if not entries:
        raise SystemExit("Ingen ONVIF Camera Control-entiteter funnet. Installer og registrer kamera først.")
    cams = _mapping(args.camera, "--camera", lambda v: v.startswith("camera."))
    names = _mapping(args.name, "--name", lambda v: bool(v.strip()))
    presets = {}
    for item in args.preset:
        entry, value = item.split("=", 1) if "=" in item else ("", "")
        label, script = value.rsplit(":", 1) if ":" in value else ("", "")
        if not entry or not label or not script.startswith("script."):
            raise SystemExit(f"Invalid --preset: {item}")
        presets.setdefault(entry, []).append((label, script))
    if any(key not in entries for key in (*cams, *names, *presets)):
        raise SystemExit("Unknown config-entry ID in --camera / --name / --preset")
    dashboard_url = "/" + args.dashboard_url.strip("/")
    output = Path(args.output)
    if output.exists() and not args.overwrite:
        raise SystemExit(f"{output} already exists. Use --overwrite to replace with a backup.")
    text = "\n".join(to_yaml(generate(entries, cams, names, presets, dashboard_url))) + "\n"
    if output.exists():
        from datetime import datetime
        backup = output.with_name(output.name + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S"))
        backup.write_bytes(output.read_bytes())
        print(f"Backup: {backup}")
    output.write_text(text, encoding="utf-8")
    print(f"OK: {len(entries)} kamera(er), {sum(map(len, entries.values()))} videostrømmer")
    print(f"Dashboard: {output}")
    for index, entry in enumerate(sorted(entries), 1):
        print(f"  {index}. {names.get(entry) or f'Kamera {index}'} | config entry ID: {entry}")
        if entry not in cams:
            print("     Ingen kamerabilde koblet til. Bruk --camera ENTRY_ID=camera.entitet")
    print("Ingen kamera- eller Home Assistant-innstillinger ble endret.")


if __name__ == "__main__":
    main()
