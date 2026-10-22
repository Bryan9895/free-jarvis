"""Posicionamento verificado de janelas no GNOME Wayland (Window Control).

Usa somente D-Bus com identidade retirada do compositor; nenhum ID arbitrário
do modelo, nenhuma manipulação direta do display ou atalhos cegos.
"""
import ast
import time

from .window_focus import _match
from .window_manage import _dbus, _inventory, EXTENSION_URL


def _select(rows, app, title):
    candidates = _match(rows, app, title)
    if not candidates:
        return None, "not_observed"
    if len(candidates) != 1:
        return None, "ambiguous"
    return candidates[0], None


def _workarea(monitor):
    proc = _dbus("GetWorkarea", monitor)
    if proc is None or proc.returncode or len(proc.stdout) > 250:
        return None
    try:
        values = ast.literal_eval(proc.stdout.strip())
    except (ValueError, SyntaxError, TypeError, MemoryError):
        return None
    if (not isinstance(values, tuple) or len(values) != 4
            or any(type(v) is not int for v in values)):
        return None
    x, y, width, height = values
    if width < 200 or height < 200 or width > 16000 or height > 16000:
        return None
    return x, y, width, height


def _half(area, side):
    x, y, width, height = area
    left_width = width // 2
    if side == "left":
        return x, y, left_width, height
    if side == "right":
        return x + left_width, y, width - left_width, height
    raise ValueError("Posição inválida; escolha left ou right")


def _rectangle(area, position, current, width_percent=None, height_percent=None,
               x_px=None, y_px=None, width_px=None, height_px=None):
    pixels = (x_px, y_px, width_px, height_px)
    if position == "custom":
        if (any(type(value) is not int for value in pixels)
                or width_percent is not None or height_percent is not None):
            raise ValueError("Posição custom exige x_px, y_px, width_px e height_px inteiros")
        ax, ay, aw, ah = area
        if (x_px < 0 or y_px < 0 or width_px < 100 or height_px < 100
                or x_px + width_px > aw or y_px + height_px > ah):
            raise ValueError("Retângulo fora da área útil do monitor")
        return ax + x_px, ay + y_px, width_px, height_px
    if any(value is not None for value in pixels):
        raise ValueError("Medidas em pixels exigem posição custom")
    if position in ("left", "right") and width_percent is None and height_percent is None:
        return _half(area, position)
    if position not in ("center", "bottom_right", "left", "right"):
        raise ValueError("Posição inválida")
    x, y, area_width, area_height = area
    for value in (width_percent, height_percent):
        if value is not None and (type(value) is not int or not 10 <= value <= 100):
            raise ValueError("Percentual deve ser inteiro entre 10 e 100")
    width = (area_width * width_percent // 100 if width_percent is not None
             else current.get("width") if position == "center" else area_width // 2)
    height = (area_height * height_percent // 100 if height_percent is not None
              else current.get("height") if position == "center" else area_height // 2)
    if type(width) is not int or type(height) is not int or width < 100 or height < 100:
        raise ValueError("Dimensões da janela indisponíveis ou pequenas demais")
    width, height = min(width, area_width), min(height, area_height)
    if position == "center":
        return x + (area_width - width) // 2, y + (area_height - height) // 2, width, height
    if position == "bottom_right":
        return x + area_width - width, y + area_height - height, width, height
    if position == "left":
        return x, y, width, height
    return x + area_width - width, y, width, height


def _identity_ok(old, new):
    return (old["id"] == new["id"] and old["app"] == new["app"]
            and old.get("pid") == new.get("pid")
            and old["title"] == new["title"])


def _run(method, *args):
    proc = _dbus(method, *args)
    if proc is None or proc.returncode:
        return False
    # MoveResize (v10+) retorna (), enquanto estados retornam (true,).
    return proc.stdout.strip().lower() in ("()", "(true,)")


def _placement_verified(before, expected, retries=4, delay=0.22):
    ex, ey, ew, eh = expected
    for attempt in range(retries):
        if attempt:
            time.sleep(delay)
        rows = _inventory()
        if rows is None:
            continue
        found = [w for w in rows if w["id"] == before["id"]
                 and w["app"] == before["app"]
                 and w.get("pid") == before.get("pid")]
        if len(found) != 1:
            continue
        win = found[0]
        # Não confundir janela minimizada com janela colocada.
        if win.get("is_minimized") is not False:
            continue
        # Mutter pode arredondar dimensões por decoração/tamanho em células.
        geometry = [win.get(key) for key in ("x", "y", "width", "height")]
        if any(type(v) is not int for v in geometry):
            continue
        if (abs(geometry[0] - ex) <= 48 and abs(geometry[1] - ey) <= 48
                and abs(geometry[2] - ew) <= 48
                and abs(geometry[3] - eh) <= 48):
            return True
    return False


def _place_one(chosen, rect):
    wid = chosen["id"]
    if chosen.get("is_minimized") is True and not _run("Unminimize", wid):
        return False
    if chosen.get("is_maximized") is True and not _run("Unmaximize", wid):
        return False
    if not _run("MoveResize", wid, *rect):
        return False
    # No GNOME real, MoveResize pode redimensionar sem mover (observado com
    # XTerm). Move separado aplica a posição; a verificação posterior continua
    # sendo a única fonte de sucesso da operação.
    _run("Move", wid, rect[0], rect[1])
    return True


def place_window(app, position, approve, title="", width_percent=None, height_percent=None,
                 x_px=None, y_px=None, width_px=None, height_px=None):
    if position not in ("left", "right", "center", "bottom_right", "custom"):
        raise ValueError("Posição deve ser left, right, center, bottom_right ou custom")
    if not isinstance(app, str) or not 2 <= len(app) <= 100:
        raise ValueError("Nome inválido")
    if not isinstance(title, str) or len(title) > 200:
        raise ValueError("Título inválido")
    before = _inventory()
    if before is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    chosen, error = _select(before, app, title)
    if error:
        return {"status": error}
    monitor = chosen.get("monitor")
    if type(monitor) is not int or monitor < 0:
        return {"status": "unavailable", "reason": "Monitor da janela desconhecido"}
    area = _workarea(monitor)
    if area is None:
        return {"status": "unavailable", "reason": "Área útil do monitor indisponível"}
    rect = _rectangle(area, position, chosen, width_percent, height_percent,
                      x_px, y_px, width_px, height_px)
    if not approve(f"POSICIONAR {chosen['app']} — {chosen['title']} em {position}, "
                   f"geometria {rect}?"):
        return {"status": "rejected"}
    current = _inventory()
    if current is None:
        return {"status": "unavailable"}
    again, error = _select(current, app, title)
    if error or not _identity_ok(chosen, again):
        return {"status": "changed", "reason": "Janela alterada antes da ação"}
    if not _place_one(chosen, rect):
        return {"status": "failed", "reason": "GNOME recusou reposicionar"}
    if _placement_verified(chosen, rect):
        return {"status": "geometry_verified", "position": position,
                "title": chosen["title"], "app": chosen["app"], "geometry": rect}
    return {"status": "geometry_unverified", "position": position,
            "reason": "Geometria final não confirmada pelo compositor"}


def arrange_windows(left_app, right_app, approve, left_title="", right_title=""):
    """Coloca duas janelas em metades da MESMA área útil, sem escolha ambígua."""
    if not all(isinstance(x, str) and 2 <= len(x) <= 100 for x in (left_app, right_app)):
        raise ValueError("Aplicativo inválido")
    if not all(isinstance(x, str) and len(x) <= 200 for x in (left_title, right_title)):
        raise ValueError("Título inválido")
    before = _inventory()
    if before is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    left, a = _select(before, left_app, left_title)
    right, b = _select(before, right_app, right_title)
    if a or b:
        return {"status": a or b, "left_problem": a, "right_problem": b}
    if left["id"] == right["id"]:
        return {"status": "ambiguous", "reason": "Selecione duas janelas diferentes"}
    monitor = left.get("monitor")
    if type(monitor) is not int or monitor < 0 or right.get("monitor") != monitor:
        return {"status": "unavailable", "reason": "Janelas em monitores diferentes"}
    area = _workarea(monitor)
    if area is None:
        return {"status": "unavailable", "reason": "Área útil do monitor indisponível"}
    if not approve(f"ORGANIZAR: {left['title']} à esquerda e {right['title']} à direita?"):
        return {"status": "rejected"}
    current = _inventory()
    if current is None:
        return {"status": "unavailable"}
    again_l, e1 = _select(current, left_app, left_title)
    again_r, e2 = _select(current, right_app, right_title)
    if (e1 or e2 or not _identity_ok(left, again_l)
            or not _identity_ok(right, again_r)):
        return {"status": "changed", "reason": "Janelas mudaram antes da ação"}
    outcomes = {}
    for side, window in (("left", left), ("right", right)):
        rect = _half(area, side)
        ok = _place_one(window, rect)
        outcomes[side] = ("geometry_verified" if ok and _placement_verified(window, rect)
                          else "geometry_unverified" if ok else "failed")
        if outcomes[side] == "failed":
            break
    if outcomes.get("left") == outcomes.get("right") == "geometry_verified":
        return {"status": "layout_verified", "left": left["title"], "right": right["title"]}
    return {"status": "layout_unverified", "outcomes": outcomes,
            "reason": "Uma ou mais janelas não tiveram geometria confirmada"}


def _grid_rectangles(area, count):
    """Três janelas: coluna esquerda e duas à direita; quatro: grade 2x2."""
    if count not in (3, 4):
        raise ValueError("A grade exige três ou quatro janelas")
    x, y, width, height = area
    left_width = width // 2
    top_height = height // 2
    if min(left_width, width - left_width, top_height, height - top_height) < 100:
        raise ValueError("Área útil pequena demais para esta grade")
    if count == 3:
        return [(x, y, left_width, height),
                (x + left_width, y, width - left_width, top_height),
                (x + left_width, y + top_height, width - left_width, height - top_height)]
    return [(x, y, left_width, top_height),
            (x + left_width, y, width - left_width, top_height),
            (x, y + top_height, left_width, height - top_height),
            (x + left_width, y + top_height, width - left_width, height - top_height)]


def arrange_window_grid(windows, approve):
    """Organiza 3–4 janelas inequívocas no mesmo monitor com verificação."""
    if not isinstance(windows, list) or len(windows) not in (3, 4):
        raise ValueError("Informe três ou quatro janelas")
    selectors = []
    for item in windows:
        if not isinstance(item, dict) or set(item) - {"app", "title"}:
            raise ValueError("Seletor de janela inválido")
        app, title = item.get("app"), item.get("title", "")
        if (not isinstance(app, str) or not 2 <= len(app) <= 100
                or not isinstance(title, str) or len(title) > 200
                or any(c in app + title for c in ("\n", "\r", "\x00"))):
            raise ValueError("Nome ou título inválido")
        selectors.append((app, title))
    before = _inventory()
    if before is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    selected = []
    for app, title in selectors:
        chosen, error = _select(before, app, title)
        if error:
            return {"status": error, "selector": {"app": app, "title": title}}
        selected.append(chosen)
    if len({item["id"] for item in selected}) != len(selected):
        return {"status": "ambiguous", "reason": "Seletores apontam para a mesma janela"}
    monitor = selected[0].get("monitor")
    if type(monitor) is not int or monitor < 0 or any(
            item.get("monitor") != monitor for item in selected):
        return {"status": "unavailable", "reason": "Janelas precisam estar no mesmo monitor"}
    area = _workarea(monitor)
    if area is None:
        return {"status": "unavailable", "reason": "Área útil do monitor indisponível"}
    rects = _grid_rectangles(area, len(selected))
    names = ", ".join(item["title"] for item in selected)
    if not approve(f"ORGANIZAR {len(selected)} JANELAS em grade no monitor {monitor}: {names}?"):
        return {"status": "rejected"}
    current = _inventory()
    if current is None:
        return {"status": "unavailable"}
    for (app, title), old in zip(selectors, selected):
        now, error = _select(current, app, title)
        if error or not _identity_ok(old, now) or now.get("monitor") != monitor:
            return {"status": "changed", "reason": "Uma janela mudou antes da ação"}
    outcomes = []
    for chosen, rect in zip(selected, rects):
        sent = _place_one(chosen, rect)
        status = ("geometry_verified" if sent and _placement_verified(chosen, rect)
                  else "geometry_unverified" if sent else "failed")
        outcomes.append({"app": chosen["app"], "title": chosen["title"],
                         "status": status, "geometry": rect})
        if status == "failed":
            break
    if len(outcomes) == len(selected) and all(
            item["status"] == "geometry_verified" for item in outcomes):
        return {"status": "layout_verified", "windows": outcomes, "monitor": monitor}
    return {"status": "layout_unverified", "outcomes": outcomes,
            "reason": "Uma ou mais janelas não tiveram geometria confirmada"}
