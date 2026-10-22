"""AT-SPI diagnostic inventory: partial by design, never a compositor window list."""
import json


def main():
    try:
        import pyatspi
    except ImportError:
        return {"status": "unavailable", "complete": False, "windows": [],
                "reason": "python3-pyatspi ausente"}
    try:
        desktop = pyatspi.Registry.getDesktop(0)
        windows = []
        apps = []
        failures = 0
        inspected = 0
        count = min(int(desktop.childCount), 100)
        for index in range(count):
            try:
                app = desktop.getChildAtIndex(index)
                if app is None:
                    continue
                app_name = str(app.name or "")[:120]
                count_children = min(int(app.childCount), 100)
                apps.append({"name": app_name, "accessible_children": count_children})
                for j in range(count_children):
                    if len(windows) >= 150:
                        break
                    try:
                        child = app.getChildAtIndex(j)
                        if child is None:
                            continue
                        inspected += 1
                        role = str(child.getRoleName() or "").lower()
                        if role in ("frame", "window", "dialog"):
                            windows.append({"app": app_name,
                                            "title": str(child.name or "")[:240],
                                            "role": role})
                    except Exception:
                        failures += 1
            except Exception:
                failures += 1
        return {
            "status": "observed", "complete": False,
            "windows": windows,
            "diagnostics": {
                "accessible_apps": apps[:100],
                "apps_seen": len(apps),
                "nodes_inspected": inspected,
                "inspection_failures": failures,
                "truncated": count >= 100 or len(windows) >= 150,
            },
            "note": "Apenas janelas publicadas por AT-SPI, não todas as janelas do GNOME."
        }
    except Exception as exc:
        return {"status": "unavailable", "complete": False, "windows": [],
                "reason": type(exc).__name__}


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False))
