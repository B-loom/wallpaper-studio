"""Traduction de l'interface.

Le francais est la langue source : les chaines ecrites dans le code sont
directement les textes affiches. Une autre langue se definit par un catalogue
JSON ``resources/lang/<code>.json`` qui associe la chaine francaise a sa
traduction.

Ajouter une langue ne demande donc aucune modification du code :

```json
{
  "_meta": {"nom": "English", "code": "en"},
  "Bibliotheque": "Library",
  "Appliquer": "Apply"
}
```

Une chaine absente du catalogue reste affichee en francais, ce qui evite les
trous dans l'interface pendant qu'une traduction est incomplete.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .app_paths import resource_dir

log = logging.getLogger(__name__)

SOURCE_LANGUAGE = "fr"

_catalog: Dict[str, str] = {}
_current = SOURCE_LANGUAGE


def lang_dir() -> Path:
    return resource_dir() / "lang"


def available_languages() -> List[Tuple[str, str]]:
    """Langues disponibles : ``(code, nom affiche)``."""
    out = [(SOURCE_LANGUAGE, "Francais")]
    directory = lang_dir()
    if not directory.is_dir():
        return out
    for item in sorted(directory.glob("*.json")):
        code = item.stem
        if code == SOURCE_LANGUAGE:
            continue
        name = code
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
            name = (data.get("_meta") or {}).get("nom", code)
        except (OSError, ValueError):
            pass
        out.append((code, name))
    return out


def set_language(code: str) -> bool:
    """Charge un catalogue. Retourne faux si la langue est introuvable."""
    global _catalog, _current
    if code == SOURCE_LANGUAGE:
        _catalog = {}
        _current = SOURCE_LANGUAGE
        return True

    path = lang_dir() / f"{code}.json"
    if not path.exists():
        log.warning("Langue introuvable : %s ; francais conserve", code)
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.error("Catalogue de langue illisible (%s) : %s", path, exc)
        return False

    _catalog = {k: v for k, v in data.items() if k != "_meta" and isinstance(v, str)}
    _current = code
    log.info("Langue active : %s (%s entrees)", code, len(_catalog))
    return True


def current_language() -> str:
    return _current


def tr(text: str, **kwargs) -> str:
    """Traduit une chaine et y insere d'eventuels parametres nommes.

    ``tr("Ecran {n}", n=2)`` fonctionne quelle que soit la langue, du moment que
    la traduction conserve le marqueur ``{n}``.
    """
    translated = _catalog.get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # Traduction mal formee : on retombe sur la chaine source.
            try:
                return text.format(**kwargs)
            except Exception:  # noqa: BLE001
                return text
    return translated


def has_translation(text: str) -> bool:
    """Vrai si le catalogue actif propose une traduction pour cette chaine."""
    return text in _catalog


def catalog_size() -> int:
    return len(_catalog)


def write_template(destination: Optional[Path] = None) -> Path:
    """Ecrit un modele de catalogue vide, utile pour demarrer une traduction."""
    destination = destination or (lang_dir() / "modele.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {"_meta": {"nom": "Nom de la langue", "code": "xx"}},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return destination
