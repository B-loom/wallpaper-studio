"""Recherche et telechargement des mises a jour publiees sur GitHub.

Fonctionnement
--------------
L'application interroge l'API publique des versions du depot
(``/releases/latest``), compare le numero de version a celui qu'elle execute,
puis, si l'utilisateur l'accepte, telecharge le fichier d'installation joint a
la publication. Rien n'est installe sans une action explicite : le
telechargement est propose, puis l'installation demande une confirmation
separee.

Prudence appliquee
------------------
* seules les adresses du depot officiel sont acceptees, en HTTPS uniquement ;
* la redirection suivie doit rester sur un domaine de GitHub ;
* le fichier est ecrit dans un dossier dedie du cache, jamais ailleurs ;
* la taille annoncee par l'API est verifiee apres telechargement ;
* l'installation n'est jamais lancee automatiquement.

Aucune donnee n'est transmise : la requete ne contient ni identifiant, ni
adresse de courriel, ni contenu de la bibliotheque.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

from .. import APP_NAME, APP_VERSION
from ..app_paths import cache_dir

log = logging.getLogger(__name__)

#: Depot officiel. Modifiable si le projet est heberge ailleurs.
GITHUB_OWNER = "B-loom"
GITHUB_REPO = "wallpaper-studio"

#: Domaines autorises pour le telechargement.
_DOMAINES_AUTORISES = (
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
)

#: Extensions acceptees pour un fichier de mise a jour.
_EXTENSIONS = (".exe", ".msi", ".zip")

_DELAI = 12.0


@dataclass(frozen=True)
class Release:
    """Une version publiee sur GitHub."""

    version: str
    nom: str
    notes: str
    url_page: str
    url_fichier: Optional[str]
    nom_fichier: Optional[str]
    taille: int = 0
    publiee_le: str = ""

    @property
    def telechargeable(self) -> bool:
        return bool(self.url_fichier)


def _version_tuple(version: str) -> Tuple[int, ...]:
    """Transforme ``v1.2.3`` en ``(1, 2, 3)`` pour une comparaison fiable.

    Une comparaison de chaines classerait « 1.10 » avant « 1.9 » ; le tri par
    nombres evite ce piege.
    """
    nombres = re.findall(r"\d+", version or "")
    return tuple(int(n) for n in nombres[:4]) or (0,)


def is_newer(candidate: str, reference: str = APP_VERSION) -> bool:
    """Vrai si ``candidate`` est strictement plus recente que ``reference``."""
    a, b = _version_tuple(candidate), _version_tuple(reference)
    longueur = max(len(a), len(b))
    a = a + (0,) * (longueur - len(a))
    b = b + (0,) * (longueur - len(b))
    return a > b


def _url_sure(url: str) -> bool:
    """Vrai si l'adresse est en HTTPS et appartient a GitHub."""
    try:
        morceaux = urlparse(url)
    except ValueError:
        return False
    if morceaux.scheme != "https":
        return False
    hote = (morceaux.hostname or "").lower()
    return any(hote == d or hote.endswith("." + d) for d in _DOMAINES_AUTORISES)


def _ouvrir(url: str):
    if not _url_sure(url):
        raise ValueError(f"adresse refusee : {url}")
    requete = urllib.request.Request(
        url,
        headers={
            # Identifiant d'application neutre, sans donnee personnelle.
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    contexte = ssl.create_default_context()
    return urllib.request.urlopen(requete, timeout=_DELAI, context=contexte)


def check_for_update(
    owner: str = GITHUB_OWNER, repo: str = GITHUB_REPO
) -> Tuple[Optional[Release], Optional[str]]:
    """Interroge GitHub. Retourne ``(version, message d'erreur)``.

    Une seule des deux valeurs est renseignee. Une absence de version
    disponible se traduit par ``(None, None)``.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        with _ouvrir(url) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, "Aucune version publiee pour l'instant."
        return None, f"GitHub a repondu {exc.code}."
    except urllib.error.URLError as exc:
        return None, f"Connexion impossible : {exc.reason}"
    except (ValueError, TimeoutError) as exc:
        return None, f"Reponse inattendue : {exc}"

    if donnees.get("draft") or donnees.get("prerelease"):
        return None, None

    version = str(donnees.get("tag_name") or donnees.get("name") or "").strip()
    if not version:
        return None, "Version sans numero."
    if not is_newer(version):
        return None, None

    url_fichier = nom_fichier = None
    taille = 0
    for fichier in donnees.get("assets") or []:
        nom = str(fichier.get("name", ""))
        if not nom.lower().endswith(_EXTENSIONS):
            continue
        adresse = str(fichier.get("browser_download_url", ""))
        if not _url_sure(adresse):
            continue
        # Un installateur est prefere a une archive.
        if url_fichier is None or nom.lower().endswith((".exe", ".msi")):
            url_fichier, nom_fichier = adresse, nom
            taille = int(fichier.get("size") or 0)

    return (
        Release(
            version=version.lstrip("vV"),
            nom=str(donnees.get("name") or version),
            notes=str(donnees.get("body") or ""),
            url_page=str(donnees.get("html_url") or ""),
            url_fichier=url_fichier,
            nom_fichier=nom_fichier,
            taille=taille,
            publiee_le=str(donnees.get("published_at") or "")[:10],
        ),
        None,
    )


def download_dir() -> Path:
    dossier = cache_dir() / "mises-a-jour"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def download_release(
    release: Release,
    on_progress: Optional[Callable[[int, int], None]] = None,
    annule: Optional[Callable[[], bool]] = None,
) -> Tuple[Optional[Path], Optional[str]]:
    """Telecharge le fichier d'une version. Retourne ``(chemin, erreur)``.

    ``on_progress`` recoit ``(octets recus, octets attendus)``. ``annule`` est
    interroge regulierement : s'il retourne vrai, le telechargement s'arrete et
    le fichier partiel est efface.
    """
    if not release.telechargeable:
        return None, "Cette version ne propose pas de fichier a telecharger."
    if not _url_sure(release.url_fichier or ""):
        return None, "Adresse de telechargement refusee."

    cible = download_dir() / (release.nom_fichier or "mise-a-jour.exe")
    partiel = cible.with_suffix(cible.suffix + ".part")

    try:
        with _ouvrir(release.url_fichier) as reponse:
            # L'adresse finale apres redirection doit rester chez GitHub.
            finale = reponse.geturl()
            if not _url_sure(finale):
                return None, "Redirection vers un domaine non autorise."

            attendu = int(reponse.headers.get("Content-Length") or release.taille or 0)
            recu = 0
            with open(partiel, "wb") as sortie:
                while True:
                    if annule is not None and annule():
                        partiel.unlink(missing_ok=True)
                        return None, None  # annulation volontaire
                    bloc = reponse.read(131072)
                    if not bloc:
                        break
                    sortie.write(bloc)
                    recu += len(bloc)
                    if on_progress:
                        on_progress(recu, attendu)
    except urllib.error.URLError as exc:
        partiel.unlink(missing_ok=True)
        return None, f"Telechargement interrompu : {exc.reason}"
    except OSError as exc:
        partiel.unlink(missing_ok=True)
        return None, f"Ecriture impossible : {exc}"

    if release.taille and recu != release.taille:
        partiel.unlink(missing_ok=True)
        return None, (
            f"Fichier incomplet : {recu} octets recus sur {release.taille} attendus."
        )

    cible.unlink(missing_ok=True)
    partiel.rename(cible)
    log.info("Mise a jour telechargee : %s (%s octets)", cible, recu)
    return cible, None


def cleanup_downloads(garder: Optional[Path] = None) -> int:
    """Efface les telechargements precedents. Retourne le nombre supprime."""
    supprimes = 0
    for fichier in download_dir().iterdir():
        if garder is not None and fichier == garder:
            continue
        try:
            fichier.unlink()
            supprimes += 1
        except OSError:
            continue
    return supprimes
