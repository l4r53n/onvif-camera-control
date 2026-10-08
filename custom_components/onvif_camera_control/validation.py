"""Validation of ONVIF video encoder settings."""


def validate_encoder_setting(options, setting, value):
    """Validate a requested H.264 encoder setting."""

    h264 = getattr(options, "H264", None)

    if h264 is None:
        raise ValueError("Camera does not report H.264 options")

    if setting == "resolution":
        supported = {
            (int(item.Width), int(item.Height))
            for item in h264.ResolutionsAvailable
        }

        if tuple(value) not in supported:
            raise ValueError(
                f"Unsupported resolution: {value}"
            )

    elif setting in ("fps", "iframe"):
        range_name = (
            "FrameRateRange"
            if setting == "fps"
            else "GovLengthRange"
        )

        limits = getattr(h264, range_name, None)

        if limits is None:
            raise ValueError(
                f"Camera does not report {setting} limits"
            )

        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{setting} must be an integer")

        if not limits.Min <= value <= limits.Max:
            raise ValueError(
                f"{setting} must be between "
                f"{limits.Min} and {limits.Max}"
            )

    else:
        raise ValueError(f"Unknown setting: {setting}")

    return True
