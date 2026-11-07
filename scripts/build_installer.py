r"""Construit l'installateur Windows de Wallpaper Studio.

Usage :
    .venv\Scripts\python.exe scripts\build_installer.py
    .venv\Scripts\python.exe scripts\build_installer.py --build

``--build`` reconstruit d'abord l'executable avec ``scripts/build.py``.
Sans cette option, le contenu de ``dist/WallpaperStudio`` est utilise tel quel.

Le resultat est ``dist/WallpaperStudio-Setup-<version>.exe``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wallpaper_studio import APP_VERSION  # noqa: E402

DIST = ROOT / "dist"
SOURCE = DIST / "WallpaperStudio"
SCRIPT = ROOT / "scripts" / "installer.iss"


def find_iscc() -> Path | None:
    """Localise le compilateur Inno Setup."""
    candidats = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    for chemin in candidats:
        if chemin.exists():
            return chemin
    trouve = shutil.which("ISCC")
    return Path(trouve) if trouve else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Construit l'installateur Windows")
    parser.add_argument("--build", action="store_true",
                        help="reconstruire l'executable avant d'empaqueter")
    args = parser.parse_args()

    print(f"Installateur de Wallpaper Studio {APP_VERSION}\n")

    if args.build:
        print("  reconstruction de l'executable...")
        resultat = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build.py"), "--clean"],
            cwd=str(ROOT), check=False,
        )
        if resultat.returncode != 0:
            print("  echec de la construction de l'executable")
            return resultat.returncode

    if not (SOURCE / "WallpaperStudio.exe").exists():
        print(f"  {SOURCE}\\WallpaperStudio.exe est introuvable.")
        print("  Lancez d'abord : python scripts\\build.py --clean")
        return 1

    iscc = find_iscc()
    if iscc is None:
        print("  Inno Setup est introuvable.")
        print("  Installez-le : winget install JRSoftware.InnoSetup")
        return 1
    print(f"  compilateur : {iscc}")

    poids = sum(f.stat().st_size for f in SOURCE.rglob("*") if f.is_file())
    print(f"  source      : {SOURCE} ({poids / 1048576:.0f} Mo)")

    commande = [
        str(iscc),
        f"/DMyAppVersion={APP_VERSION}",
        f"/DMySourceDir={SOURCE}",
        str(SCRIPT),
    ]
    print("\n  compression en cours (quelques minutes)...\n")
    debut = time.time()
    resultat = subprocess.run(commande, cwd=str(ROOT / "scripts"), check=False)
    duree = time.time() - debut

    if resultat.returncode != 0:
        print(f"\n  echec de la compilation (code {resultat.returncode})")
        return resultat.returncode

    cible = DIST / f"WallpaperStudio-Setup-{APP_VERSION}.exe"
    if not cible.exists():
        print(f"\n  Inno Setup a termine mais {cible.name} est introuvable")
        return 1

    taille = cible.stat().st_size / 1048576
    print(f"\n  Installateur construit en {duree:.0f} s")
    print(f"    fichier : {cible}")
    print(f"    taille  : {taille:.0f} Mo  (source {poids / 1048576:.0f} Mo)")
    print("\n  Verification conseillee :")
    print(f'    "{cible}" /SILENT')
    return 0


if __name__ == "__main__":
    sys.exit(main())
