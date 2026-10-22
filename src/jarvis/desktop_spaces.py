"""Inventário somente leitura de monitores e áreas de trabalho do GNOME."""
import ast
import json

from .window_manage import _dbus, EXTENSION_URL
from .window_layout import _workarea


def _rows(method, limit):
    response = _dbus(method)
    if response is None or response.returncode or len(response.stdout) > 32_000:
        return None
    try:
        reply = ast.literal_eval(response.stdout.strip())
        if not isinstance(reply, tuple) or len(reply) != 1 or not isinstance(reply[0], str):
            return None
        rows = json.loads(reply[0])
    except (ValueError, SyntaxError, TypeError, MemoryError):
        return None
    if not isinstance(rows, list) or not 1 <= len(rows) <= limit:
        return None
    return rows


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _plain(value, maximum):
    return (isinstance(value, str) and len(value) <= maximum
            and not any(ord(char) < 32 for char in value))


def _monitors():
    rows = _rows("ListMonitors", 16)
    if rows is None:
        return None
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        index = row.get("index")
        x, y, width, height = (row.get(key) for key in ("x", "y", "width", "height"))
        scale = row.get("scale")
        primary = row.get("is_primary")
        connector = row.get("connector", "")
        if (not _integer(index, 0, 64) or index in seen
                or not _integer(x, -100_000, 100_000)
                or not _integer(y, -100_000, 100_000)
                or not _integer(width, 200, 16_000)
                or not _integer(height, 200, 16_000)
                or type(scale) not in (int, float) or not 0.5 <= scale <= 8
                or type(primary) is not bool or not _plain(connector, 100)):
            return None
        seen.add(index)
        item = {"index": index, "x": x, "y": y, "width": width,
                "height": height, "scale": scale, "is_primary": primary,
                "connector": connector}
        area = _workarea(index)
        if (area is not None and area[0] >= x and area[1] >= y
                and area[0] + area[2] <= x + width
                and area[1] + area[3] <= y + height):
            item["workarea"] = area
        result.append(item)
    if sum(item["is_primary"] for item in result) != 1:
        return None
    return result


def _workspaces():
    rows = _rows("ListWorkspaces", 64)
    if rows is None:
        return None
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        index = row.get("index")
        name = row.get("name", "")
        active = row.get("is_active")
        count = row.get("window_count")
        if (not _integer(index, 0, 63) or index in seen
                or not _plain(name, 120) or type(active) is not bool
                or not _integer(count, 0, 1000)):
            return None
        seen.add(index)
        result.append({"index": index, "name": name,
                       "is_active": active, "window_count": count})
    if sum(item["is_active"] for item in result) != 1:
        return None
    return result


def desktop_spaces():
    """Retorna inventário do compositor sem controlar áreas ou janelas."""
    monitors = _monitors()
    workspaces = _workspaces()
    if monitors is None or workspaces is None:
        return {"status": "unavailable", "reason": "Inventário de monitores ou áreas de trabalho indisponível",
                "install_url": EXTENSION_URL}
    return {"status": "observed", "source": "gnome_window_control",
            "monitors": monitors, "workspaces": workspaces,
            "active_workspace": next(row["index"] for row in workspaces if row["is_active"])}
