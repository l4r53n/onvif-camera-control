"""Friendly encoder names based on current encoder resolutions."""


def stream_name(coordinator, token):
    """Label streams by resolution, without assuming ONVIF token names."""
    stable_names = getattr(coordinator, "stream_names", {})
    if token in stable_names:
        return stable_names[token]
    data = getattr(coordinator, "data", None) or {}
    if not isinstance(data, dict) or token not in data:
        return "Videostrøm"

    def pixels(key):
        item = data.get(key) or {}
        try:
            return int(item.get("width", 0)) * int(item.get("height", 0))
        except (TypeError, ValueError, AttributeError):
            return 0

    tokens = sorted(data, key=lambda key: (-pixels(key), str(key)))
    pos = tokens.index(token)
    return ("Hovedstrøm" if pos == 0 else
            "Sekundærstrøm" if pos == 1 else
            f"Videostrøm {pos + 1}")
