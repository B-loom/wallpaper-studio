# Licences des composants

Wallpaper Studio est une creation originale. Il s'inspire des
*fonctionnalites* offertes par les gestionnaires de fonds d'ecran existants,
sans reutiliser leur code source, leurs ressources graphiques, leurs formats de
fichiers proprietaires ni leurs donnees internes.

Les icones, l'identite graphique, le fond d'ecran web d'exemple et l'ensemble
du code de ce depot sont des creations propres au projet.

---

## Composants tiers

### PySide6 / Qt 6 — LGPL v3

Interface graphique, rendu, et QtWebEngine pour les fonds d'ecran web.

- Site : https://www.qt.io/qt-for-python
- L'application **se lie dynamiquement** a Qt, sans modifier ses bibliotheques.
- La LGPL v3 autorise cette utilisation. Elle impose de permettre le
  remplacement des bibliotheques Qt par une version differente : la
  distribution en dossier (`--onedir`, mode par defaut du script de
  construction) satisfait cette obligation, puisque les DLL Qt y sont des
  fichiers distincts et remplacables.
- Texte de la licence : https://www.gnu.org/licenses/lgpl-3.0.html

> Note : QtWebEngine embarque Chromium, lui-meme couvert par la licence BSD a
> 3 clauses et diverses licences compatibles. Le detail est fourni dans
> `_internal/PySide6/resources/` du paquet construit.

### libVLC — LGPL v2.1 ou ulterieure

Lecture des fichiers video.

- Site : https://www.videolan.org/vlc/libvlc.html
- L'application **se lie dynamiquement** a `libvlc.dll`, sans la modifier.
- Par defaut, l'application utilise le VLC **installe sur la machine** et ne
  redistribue donc rien.
- Avec l'option `--with-vlc`, `libvlc.dll`, `libvlccore.dll` et le dossier
  `plugins` sont copies dans le paquet. Cette redistribution est permise par la
  LGPL v2.1 : les bibliotheques ne sont pas modifiees et restent des fichiers
  distincts, remplacables par l'utilisateur.
- Texte de la licence : https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

> Attention : certains greffons de VLC peuvent etre couverts par la GPL selon
> la compilation retenue. Si vous redistribuez un paquet avec `--with-vlc`,
> verifiez les licences des greffons presents dans votre installation de VLC.

### python-vlc — LGPL v2.1 ou ulterieure

Liaison Python vers libVLC.

- Site : https://wiki.videolan.org/PythonBinding

### Pillow — licence MIT-CMU

Decodage et traitement des images, y compris APNG et WEBP anime.

- Site : https://python-pillow.github.io/
- Licence permissive, aucune obligation particuliere hors mention du copyright.

### psutil — licence BSD a 3 clauses

Mesure de la memoire et de la charge processeur.

- Site : https://github.com/giampaolo/psutil

### FFmpeg — LGPL v2.1+ ou GPL v2+ selon la compilation

**Composant facultatif**, non redistribue avec l'application.

- Site : https://ffmpeg.org/
- Utilise pour les vignettes de videos, la lecture des metadonnees
  (`ffprobe`) et le module de conversion.
- L'application l'appelle comme un **programme externe** et ne l'incorpore pas :
  aucune obligation de licence ne se propage au code de Wallpaper Studio.
- Si vous choisissez de distribuer FFmpeg avec l'application, respectez la
  licence de la version que vous embarquez. Les versions compilees avec des
  composants GPL (comme `libx264`) imposent la GPL a l'ensemble du paquet
  redistribue.

### PyInstaller — GPL v2 avec exception

Outil de construction uniquement.

- Site : https://pyinstaller.org/
- L'exception de licence de PyInstaller autorise explicitement la distribution
  des executables produits sous la licence de votre choix. PyInstaller n'est
  pas inclus dans l'application livree.

### pytest — licence MIT

Outil de test uniquement, non distribue avec l'application.

---

## Resume des obligations en cas de redistribution

| Situation | Obligations |
|---|---|
| Distribution sans libVLC ni FFmpeg | Mentionner Qt (LGPL v3), Pillow, psutil ; fournir les DLL Qt sous forme remplacable |
| Distribution avec `--with-vlc` | Ajouter la mention LGPL v2.1 de libVLC et verifier les licences des greffons |
| Distribution avec FFmpeg embarque | Respecter la licence de la version embarquee ; une version GPL impose la GPL au paquet |

Dans tous les cas, conserver ce fichier `LICENSES.md` a cote de l'application
et rendre accessible le texte des licences citees.
