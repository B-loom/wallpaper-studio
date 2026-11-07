r"""Construction de l'executable Windows de Wallpaper Studio.

Usage :
    .venv\Scripts\python.exe scripts\build.py              version portable (un dossier)
    .venv\Scripts\python.exe scripts\build.py --onefile    fichier unique
    .venv\Scripts\python.exe scripts\build.py --with-vlc   embarque libVLC
    .venv\Scripts\python.exe scripts\build.py --clean      nettoie avant de construire

Le resultat est place dans ``dist/``.

Note sur libVLC : par defaut, l'executable utilise le VLC installe sur la
machine (detecte au lancement). ``--with-vlc`` copie la bibliotheque dans le
paquet pour obtenir une version autonome ; voir ``LICENSES.md`` pour les
obligations LGPL correspondantes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DIST = ROOT / "dist"
BUILD = ROOT / "build"
NAME = "WallpaperStudio"

#: Modules Qt inutiles a l'application : les exclure allege nettement le paquet.
EXCLUDES = [
    "PySide6.QtQuick3D", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "tkinter", "unittest", "pydoc_data", "pytest", "_pytest",
    "matplotlib", "numpy", "scipy", "pandas",
]

#: Modules charges dynamiquement que PyInstaller ne peut pas deviner.
HIDDEN_IMPORTS = [
    "vlc",
    "wallpaper_studio.engine.backends.web_backend",
    "wallpaper_studio.engine.backends.video_vlc",
    "wallpaper_studio.engine.backends.image_backend",
    "PIL.Image", "PIL.ImageEnhance", "PIL.ImageFilter", "PIL.ImageSequence",
]


def make_icon() -> Path:
    """Genere l'icone .ico a partir du dessin vectoriel de l'application."""
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    from wallpaper_studio.ui.theme import app_icon

    target = ROOT / "resources" / "icons" / "wallpaper-studio.ico"
    target.parent.mkdir(parents=True, exist_ok=True)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        pixmap = app_icon(size).pixmap(size, size)
        path = BUILD / f"icon_{size}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(path), "PNG")
        images.append(path)

    from PIL import Image

    base = Image.open(images[-1])
    base.save(target, format="ICO", sizes=[(s, s) for s in sizes])
    for path in images:
        path.unlink(missing_ok=True)
    print(f"  icone generee : {target}")
    return target


def find_vlc() -> Path | None:
    from wallpaper_studio.engine.backends.vlc_runtime import find_vlc_dir

    return find_vlc_dir()


#: Fichiers inutiles en production que PyInstaller embarque malgre tout.
#: Les ressources « devtools » de QtWebEngine pesent a elles seules 80 Mo et ne
#: servent qu'au debogage de pages web.
_PRUNE_PATTERNS = [
    "PySide6/resources/qtwebengine_devtools_resources.debug.pak",
    "PySide6/resources/qtwebengine_devtools_resources.pak",
    "PySide6/translations/qtwebengine_locales/*.pak",
]
#: Langues conservees pour QtWebEngine (l'interface est en francais).
_KEEP_LOCALES = {"fr.pak", "en-US.pak"}


def prune_package(folder: Path | None) -> float:
    """Supprime les ressources inutiles. Retourne les megaoctets liberes."""
    if folder is None or not folder.exists():
        return 0.0
    internal = folder / "_internal"
    base = internal if internal.exists() else folder
    freed = 0

    for pattern in _PRUNE_PATTERNS:
        for path in base.glob(pattern):
            if path.parent.name == "qtwebengine_locales" and path.name in _KEEP_LOCALES:
                continue
            try:
                freed += path.stat().st_size
                path.unlink()
            except OSError:
                continue
    return freed / (1024 * 1024)


def build(onefile: bool, with_vlc: bool, clean: bool, no_web: bool = False) -> int:
    print(f"Construction de {NAME}\n")

    if clean:
        for folder in (DIST, BUILD):
            if folder.exists():
                print(f"  nettoyage de {folder.name}/")
                shutil.rmtree(folder, ignore_errors=True)

    icon = make_icon()

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",                 # pas de console
        "--name", NAME,
        "--icon", str(icon),
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        # Ressources embarquees : icones, modeles de fonds web, traductions.
        "--add-data", f"{ROOT / 'resources'}{';'}resources",
    ]

    args.append("--onefile" if onefile else "--onedir")

    for module in HIDDEN_IMPORTS:
        args += ["--hidden-import", module]
    for module in EXCLUDES:
        args += ["--exclude-module", module]

    if no_web:
        # Sans QtWebEngine, le paquet perd environ 300 Mo mais les fonds web
        # ne sont plus disponibles. L'application le detecte et le signale.
        print("  QtWebEngine exclu : les fonds web ne seront pas disponibles")
        for module in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
                       "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
                       "PySide6.QtPdf", "PySide6.QtPdfWidgets"):
            args += ["--exclude-module", module]

    if with_vlc:
        vlc_dir = find_vlc()
        if vlc_dir is None:
            print("  ATTENTION : VLC introuvable, --with-vlc ignore")
        else:
            print(f"  libVLC embarquee depuis {vlc_dir}")
            args += [
                "--add-binary", f"{vlc_dir / 'libvlc.dll'}{';'}vlc",
                "--add-binary", f"{vlc_dir / 'libvlccore.dll'}{';'}vlc",
                "--add-data", f"{vlc_dir / 'plugins'}{';'}vlc/plugins",
            ]

    args.append(str(ROOT / "main.py"))

    print("  lancement de PyInstaller...\n")
    started = time.time()
    result = subprocess.run(args, cwd=str(ROOT), check=False)
    elapsed = time.time() - started

    if result.returncode != 0:
        print(f"\nEchec de la construction (code {result.returncode})")
        return result.returncode

    target = DIST / f"{NAME}.exe" if onefile else DIST / NAME / f"{NAME}.exe"
    if not target.exists():
        print(f"\nPyInstaller a termine mais {target} est introuvable")
        return 1

    trimmed = prune_package(DIST / NAME if not onefile else None)
    if trimmed:
        print(f"  allege de {trimmed:.0f} Mo (ressources de developpement Qt)")

    # Mesuree apres allegement, pour annoncer la taille reellement distribuee.
    size_mb = (
        target.stat().st_size / (1024 * 1024)
        if onefile
        else sum(f.stat().st_size for f in (DIST / NAME).rglob("*") if f.is_file())
        / (1024 * 1024)
    )

    # Mode portable : le marqueur fait vivre les donnees a cote de l'executable.
    if not onefile:
        marker = DIST / NAME / "portable.txt"
        marker.write_text(
            "La presence de ce fichier place les donnees de l'application "
            "dans le sous-dossier data/ plutot que dans %LOCALAPPDATA%.\n"
            "Supprimez-le pour une installation classique.\n",
            encoding="utf-8",
        )

    print(f"\nConstruction terminee en {elapsed:.0f} s")
    print(f"  executable : {target}")
    print(f"  taille     : {size_mb:.0f} Mo")
    print("\nTest conseille :")
    print(f'  "{target}" --selftest')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Construit l'executable Windows")
    parser.add_argument("--onefile", action="store_true",
                        help="produire un fichier .exe unique (demarrage plus lent)")
    parser.add_argument("--with-vlc", action="store_true",
                        help="embarquer libVLC pour un paquet autonome")
    parser.add_argument("--clean", action="store_true",
                        help="supprimer dist/ et build/ avant de construire")
    parser.add_argument("--no-web", action="store_true",
                        help="exclure QtWebEngine : paquet ~300 Mo plus leger, "
                             "mais sans les fonds d'ecran web")
    args = parser.parse_args()
    return build(args.onefile, args.with_vlc, args.clean, args.no_web)


if __name__ == "__main__":
    sys.exit(main())
