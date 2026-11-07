"""Diagnostic du rendu : verifie que le fond s'affiche vraiment sur le bureau.

Pourquoi ce module existe
-------------------------
Verifier « a l'oeil » qu'un fond d'ecran s'affiche est plus delicat qu'il n'y
parait : le bureau est presque toujours recouvert par des fenetres, et une
capture d'ecran classique montre donc les applications, pas le fond. Par
ailleurs ``PrintWindow`` sur la couche ``WorkerW`` ne restitue pas de maniere
fiable les fenetres appartenant a un autre processus.

La seule methode concluante consiste donc a :

1. afficher une mire reconnaissable sur le bureau ;
2. reduire toutes les fenetres (comme ``Win + D``) ;
3. capturer l'ecran reel ;
4. restaurer les fenetres ;
5. analyser la capture pour y retrouver les couleurs de la mire.

Les fenetres sont restaurees meme en cas d'erreur, afin de ne jamais laisser la
session de l'utilisateur dans un etat inattendu.
"""

from __future__ import annotations

import ctypes
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from . import win_desktop as wd
from .monitors import enumerate_monitors

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)

#: Couleurs de la mire : volontairement saturees et rares sur un bureau normal.
MIRE_MAGENTA = (255, 0, 200)
MIRE_CYAN = (0, 220, 255)

#: Part minimale de pixels de la mire pour conclure qu'elle est visible.
SEUIL_DETECTION = 0.08


@dataclass
class DiagnosticResult:
    """Resultat complet du diagnostic."""

    host_found: bool = False
    host_layout: str = ""
    host_is_fallback: bool = False
    hides_icons: bool = False
    rivals: List[str] = field(default_factory=list)
    surface_attached: bool = False
    surface_zorder: Optional[int] = None
    layer_children: List[Tuple[int, str]] = field(default_factory=list)
    capture_path: Optional[Path] = None
    mire_ratio: float = 0.0
    mire_visible: bool = False
    monitors: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.mire_visible and self.surface_attached and self.error is None

    def explain(self) -> str:
        """Diagnostic en francais, avec la cause probable en cas d'echec."""
        if self.error:
            return f"Le diagnostic n'a pas pu aller au bout : {self.error}"
        if self.success and self.hides_icons:
            return (
                "Le fond d'ecran s'affiche bien sur le bureau. Sur cette "
                "version de Windows, il est dessine dans la couche des icones "
                "et les recouvre donc tant qu'il est actif : c'est une limite "
                "du systeme, pas un reglage."
            )
        if self.success:
            return (
                "Le fond d'ecran s'affiche bien sur le bureau, derriere les "
                "icones. Le moteur fonctionne sur cette machine."
            )
        if not self.host_found:
            return (
                "La couche de fond d'ecran de Windows est introuvable. "
                "L'Explorateur Windows est-il bien demarre ?"
            )
        if not self.surface_attached:
            return (
                "La fenetre de fond n'a pas pu etre rattachee a la couche du "
                "bureau. Windows a peut-etre refuse l'operation."
            )
        if self.rivals:
            return (
                f"La mire n'a pas ete detectee et {', '.join(self.rivals)} occupe "
                "la meme couche : cet autre logiciel passe probablement devant. "
                "Fermez-le puis relancez le diagnostic."
            )
        if self.surface_zorder is not None and self.surface_zorder > 0:
            return (
                "La mire n'a pas ete detectee : une autre fenetre de la couche "
                "de bureau se trouve au-dessus de la notre."
            )
        if self.host_is_fallback:
            return (
                "La mire n'a pas ete detectee et le rendu utilise Progman en "
                "mode de repli. Redemarrez l'Explorateur Windows et reessayez."
            )
        return (
            "La mire n'a pas ete detectee alors que la fenetre est correctement "
            "rattachee. Une capture d'ecran a ete enregistree : ouvrez-la pour "
            "voir ce que Windows affichait a cet instant."
        )


def build_test_pattern(destination: Path, size=(1280, 720)) -> Path:
    """Genere la mire de test : damier magenta / cyan et texte explicite."""
    from PIL import Image, ImageDraw

    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)

    cell_w, cell_h = width // 8, height // 8
    for row in range(8):
        for col in range(8):
            colour = MIRE_MAGENTA if (row + col) % 2 == 0 else MIRE_CYAN
            draw.rectangle(
                [col * cell_w, row * cell_h,
                 (col + 1) * cell_w - 1, (row + 1) * cell_h - 1],
                fill=colour,
            )

    band_top = int(height * 0.38)
    band_bottom = int(height * 0.62)
    draw.rectangle([0, band_top, width, band_bottom], fill=(12, 14, 20))
    draw.text(
        (int(width * 0.08), band_top + 40),
        "WALLPAPER STUDIO - TEST D'AFFICHAGE",
        fill=(255, 235, 60),
    )
    draw.text(
        (int(width * 0.08), band_top + 70),
        "Si vous voyez ceci sur votre bureau, le moteur fonctionne.",
        fill=(255, 255, 255),
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination


def _shell():
    """Objet COM Shell.Application, ou ``None`` s'il est indisponible."""
    try:
        import win32com.client

        return win32com.client.Dispatch("Shell.Application")
    except Exception as exc:  # noqa: BLE001
        log.warning("Shell.Application indisponible : %s", exc)
        return None


def minimize_all_windows() -> bool:
    """Reduit toutes les fenetres, equivalent de ``Win + D``."""
    shell = _shell()
    if shell is None:
        return False
    try:
        shell.MinimizeAll()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Reduction des fenetres impossible : %s", exc)
        return False


def restore_all_windows() -> bool:
    """Restaure les fenetres reduites par :func:`minimize_all_windows`."""
    shell = _shell()
    if shell is None:
        return False
    try:
        shell.UndoMinimizeALL()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Restauration des fenetres impossible : %s", exc)
        return False


def _mire_ratio(image) -> float:
    """Part des pixels correspondant aux couleurs de la mire."""
    small = image.convert("RGB").resize((160, 90))
    pixels = list(small.getdata())
    hits = 0
    for r, g, b in pixels:
        magenta = r > 200 and g < 90 and 150 < b < 235
        cyan = r < 90 and g > 180 and b > 200
        if magenta or cyan:
            hits += 1
    return hits / len(pixels) if pixels else 0.0


def run_diagnostic(
    output_dir: Path,
    hold_seconds: float = 2.5,
    auto_minimize: bool = True,
) -> DiagnosticResult:
    """Execute le diagnostic complet et retourne son resultat.

    Doit etre appele depuis une ``QApplication`` deja creee.
    """
    from PySide6.QtWidgets import QApplication

    from ..engine.backends.image_backend import ImageBackend
    from ..engine.playback import PlaybackRequest
    from ..engine.surface import WallpaperSurface
    from ..media.types import FillMode, MediaKind

    result = DiagnosticResult()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result.rivals = wd.detect_rival_wallpaper_apps()
    monitors = enumerate_monitors()
    result.monitors = len(monitors)
    if not monitors:
        result.error = "aucun ecran detecte"
        return result

    host = wd.find_wallpaper_host()
    if host is None:
        return result
    result.host_found = True
    result.host_layout = host.layout
    result.host_is_fallback = host.is_fallback
    result.hides_icons = host.hides_desktop_icons

    pattern = build_test_pattern(output_dir / "mire_test.png")

    surface = WallpaperSurface(monitors[0])
    backend = ImageBackend(
        PlaybackRequest(path=str(pattern), kind=MediaKind.IMAGE,
                        fill_mode=FillMode.COVER)
    )
    surface.set_content(backend.widget())

    minimized = False
    try:
        result.surface_attached = surface.attach(host)
        backend.start()
        QApplication.processEvents()

        children = wd.iter_children(host.hwnd)
        result.layer_children = [(h, wd.window_class(h)) for h in children]
        our_hwnd = surface.hwnd()
        if our_hwnd in children:
            result.surface_zorder = children.index(our_hwnd)

        # Laisse Qt peindre la mire avant de capturer.
        deadline = time.time() + 1.0
        while time.time() < deadline:
            QApplication.processEvents()
            time.sleep(0.05)

        if auto_minimize:
            minimized = minimize_all_windows()
            time.sleep(0.9)  # laisse l'animation de reduction se terminer

        QApplication.processEvents()
        time.sleep(hold_seconds if minimized else 0.3)

        from PIL import ImageGrab

        shot = ImageGrab.grab()
        result.capture_path = output_dir / "bureau_diagnostic.png"
        shot.save(result.capture_path)
        result.mire_ratio = _mire_ratio(shot)
        result.mire_visible = result.mire_ratio >= SEUIL_DETECTION

    except Exception as exc:  # noqa: BLE001 - le diagnostic ne doit jamais planter
        log.exception("Diagnostic interrompu")
        result.error = str(exc)
    finally:
        # Quoi qu'il arrive, on rend sa session a l'utilisateur.
        if minimized:
            restore_all_windows()
        try:
            backend.stop()
            surface.detach()
            surface.close()
            wd.refresh_desktop()
        except Exception:  # noqa: BLE001
            pass

    return result


def format_report(result: DiagnosticResult) -> str:
    """Rapport lisible, destine a la console."""
    lines = ["", "=" * 62, "  DIAGNOSTIC D'AFFICHAGE DU FOND D'ECRAN", "=" * 62, ""]

    def ligne(label: str, value: str) -> None:
        lines.append(f"  {label:<32} {value}")

    ligne("Ecrans detectes", str(result.monitors))
    ligne("Couche de bureau trouvee", "oui" if result.host_found else "NON")
    if result.host_found:
        agencement = {
            wd.LAYOUT_SIBLING: "WorkerW soeur (Windows 10)",
            wd.LAYOUT_PROGMAN_CHILD: "WorkerW enfant de Progman (Windows 11)",
            wd.LAYOUT_DEFVIEW_OVERLAY:
                "SHELLDLL_DefView (Windows 11 recent, recouvre les icones)",
            wd.LAYOUT_PROGMAN_FALLBACK: "Progman (mode de repli degrade)",
        }.get(result.host_layout, result.host_layout)
        ligne("Agencement", agencement)
    ligne("Autres logiciels de fond", ", ".join(result.rivals) or "aucun")
    ligne("Fenetre rattachee", "oui" if result.surface_attached else "NON")
    ligne(
        "Position dans la couche",
        "au sommet" if result.surface_zorder == 0
        else (f"z={result.surface_zorder}" if result.surface_zorder is not None
              else "absente"),
    )

    if result.layer_children:
        lines.append("")
        lines.append("  Contenu de la couche de bureau :")
        for index, (hwnd, classe) in enumerate(result.layer_children):
            marque = "  <-- notre fenetre" if index == result.surface_zorder else ""
            lines.append(f"      z={index}  {classe} (hwnd={hwnd}){marque}")

    lines.append("")
    ligne("Mire detectee a l'ecran", f"{result.mire_ratio * 100:.1f} % des pixels")
    ligne("Icones du bureau", "recouvertes" if result.hides_icons else "visibles")
    ligne("Verdict", "REUSSI" if result.success else "ECHEC")
    if result.capture_path:
        lines.append("")
        ligne("Capture enregistree", str(result.capture_path))

    lines.append("")
    lines.append("  " + result.explain())
    lines.append("")
    lines.append("=" * 62)
    return "\n".join(lines)
