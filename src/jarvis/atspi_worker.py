"""Read-only inventory of accessible GNOME application windows."""
import json

def main():
    try:
        import pyatspi
    except ImportError:
        return {"status":"unavailable","windows":[],"reason":"python3-pyatspi ausente"}
    desktop=pyatspi.Registry.getDesktop(0)
    windows=[]
    for app in list(desktop)[:80]:
        try:
            for child in list(app)[:80]:
                if child and child.getRoleName().lower() in ("frame","window","dialog"):
                    windows.append({"app":str(app.name or "")[:120],"title":str(child.name or "")[:240]})
        except Exception:
            continue
    return {"status":"observed","windows":windows[:120]}

if __name__=="__main__":
    try:
        print(json.dumps(main(),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"status":"unavailable","windows":[],"reason":type(exc).__name__}))
