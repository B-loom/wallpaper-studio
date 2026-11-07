# Wallpaper Studio

Gestionnaire de fonds d'écran animés pour Windows : images, GIF, vidéos et fonds
web, avec gestion multi-écrans et **programmation horaire automatique** (fond de
jour / fond de nuit).

Interface en français, thème sombre, fonctionnement en arrière-plan depuis la
zone de notification.

---

## Sommaire

- [Présentation](#présentation)
- [État des fonctionnalités](#état-des-fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Langue de l'interface](#langue-de-linterface)
- [Mises à jour](#mises-à-jour)
- [Utilisation](#utilisation)
- [Configuration des horaires](#configuration-des-horaires)
- [Gestion des écrans](#gestion-des-écrans)
- [Fonds d'écran web](#fonds-décran-web)
- [Formats pris en charge](#formats-pris-en-charge)
- [Performances](#performances)
- [Compilation](#compilation)
- [Tests](#tests)
- [Emplacement des fichiers](#emplacement-des-fichiers)
- [Résolution des problèmes](#résolution-des-problèmes)
- [Architecture](#architecture)
- [Dépendances et licences](#dépendances-et-licences)

---

## Présentation

Wallpaper Studio affiche un contenu animé **derrière les icônes du
bureau**, à la place du fond d'écran statique de Windows. Il s'appuie sur la
couche `WorkerW` de l'Explorateur Windows (voir
[Architecture](#architecture) pour les détails techniques et les limites).

La fonctionnalité centrale est le **planificateur horaire** : vous définissez
des plages (par exemple 08h00–22h00 et 22h00–08h00) et le logiciel change de
fond tout seul, y compris après une mise en veille ou un redémarrage.

---

## État des fonctionnalités

### Terminé et testé

| Domaine | Détail |
|---|---|
| Moteur de rendu | Images fixes, images animées, vidéos, fonds web, derrière les icônes |
| Multi-écrans | Détection, configuration indépendante par écran, clé matérielle stable |
| Planificateur | Plages horaires, passage à minuit, jours de la semaine, priorités, conflits, par écran |
| Bibliothèque | Import fichiers/dossier/glisser-déposer, tags, collections, favoris, recherche, filtres, tri |
| Éditeur | Luminosité, contraste, saturation, teinte, flou, rotation, miroirs, cadrage, presets |
| Effets | 8 effets de particules réellement dessinés (voir plus bas) |
| Performances | Pause automatique, plafond FPS, profils, mesures RAM/CPU |
| Arrière-plan | Zone de notification, démarrage avec Windows, fermeture sans arrêt du moteur |
| Paramètres | 21 réglages, tous effectifs, sauvegarde et restauration |
| Conversion | Vidéo→GIF, GIF→images, images→vidéo, extraction d'image, réencodage |
| Exécutable | Version portable `.exe` construite et testée |

### Partiellement implémenté

| Fonctionnalité | Limite actuelle |
|---|---|
| Mode panoramique | Images fixes uniquement ; une vidéo ne peut pas être répartie sur plusieurs écrans |
| Interactivité souris | Position du curseur transmise aux effets et aux fonds web ; les **clics** ne sont pas transmis (limite de Windows, voir [Architecture](#architecture)) |
| Fonds web | Exécution isolée fonctionnelle ; pas de magasin de contenus ni d'éditeur web intégré |
| Vitesse de lecture | Réglable pour les vidéos et les GIF ; la position de lecture est lisible mais il n'y a pas de curseur de navigation |
| Thème clair | Palette complète et fonctionnelle, moins travaillée que le thème sombre |

### Non implémenté

Ces points figuraient dans le cahier des charges initial et **ne sont pas
présents** dans cette version :

- **Réaction au son / visualisation audio.** Capter la sortie audio de Windows
  demande une boucle de capture WASAPI et une analyse spectrale temps réel. Ce
  n'est pas fait. Un fond web peut en revanche utiliser sa propre source audio.
- **Effet de parallaxe.** L'infrastructure d'effets le permettrait, mais aucun
  effet de parallaxe n'est écrit à ce jour.
- **Éditeur de scènes animées.** Il n'y a pas d'outil de composition de scènes ;
  les effets se choisissent dans une liste, ils ne se dessinent pas.
- **Météo intégrée.** Aucune source météo n'est fournie. Un fond web peut en
  utiliser une, à condition d'autoriser explicitement son accès réseau.
- **Charge GPU.** Non mesurable sans bibliothèque constructeur ; la page
  Performances l'indique comme « non mesurée » plutôt que d'afficher un chiffre
  inventé.
- **Programme d'installation.** Seule la version portable est produite. Voir
  [Compilation](#compilation).

---

## Prérequis

### Pour utiliser l'exécutable

- Windows 10 version 1809 ou ultérieure, ou Windows 11 (64 bits).
- **VLC 64 bits** installé, *ou* une version compilée avec `--with-vlc`.
  Sans libVLC, les images et les fonds web fonctionnent, mais pas les vidéos.
- FFmpeg est **facultatif** : il améliore les vignettes de vidéos, les
  métadonnées et active le module de conversion.

Python n'est **pas** nécessaire pour lancer l'exécutable.

### Pour développer

- Python 3.11 (PySide6 6.12 ne propose pas encore de roue pour Python 3.14).
- Les paquets de `requirements.txt`.

---

## Installation

### Version portable (recommandée)

1. Décompressez le dossier `WallpaperStudio`.
2. Lancez `WallpaperStudio.exe`.

Le fichier `portable.txt` présent à côté de l'exécutable place toutes les
données dans le sous-dossier `data\`. Supprimez-le pour utiliser
`%LOCALAPPDATA%` à la place.

### Depuis les sources

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Vérifiez d'abord que l'environnement est complet :

```bat
.venv\Scripts\python.exe main.py --selftest
```

Cette commande affiche la version de Python, la couche de bureau détectée, les
écrans, la présence de libVLC, de FFmpeg et de QtWebEngine.

---

## Langue de l'interface

Au **tout premier lancement**, Wallpaper Studio demande la langue : français ou
anglais. Le choix est modifiable à tout moment dans *Paramètres → Langue*.

Le français est la langue source : les textes sont écrits en français dans le
code, et une traduction est appliquée à l'ouverture de chaque page. Les notes
de version suivent la même langue (page *Nouveautés*).

### Ajouter une langue

Déposez un fichier `resources/lang/<code>.json` associant la chaîne française à
sa traduction, sans toucher au code :

```json
{
  "_meta": {"nom": "Español", "code": "es"},
  "Bibliotheque": "Biblioteca",
  "Horaires": "Horarios"
}
```

La langue apparaît alors dans les paramètres. Une chaîne absente du catalogue
reste affichée en français, ce qui évite les trous dans l'interface pendant
qu'une traduction est incomplète. Les notes de version se traduisent en
ajoutant `resources/changelog/<code>.md`.

> Limite assumée : les messages composés à l'exécution (« 12 fonds affichés sur
> 30 ») restent en français. Les libellés fixes, c'est-à-dire l'essentiel de
> l'interface, sont bien traduits.

## Mises à jour

Wallpaper Studio consulte la page des versions publiées du projet sur GitHub et
vous prévient quand une version plus récente existe. Rien n'est installé sans
votre accord, en trois étapes distinctes :

1. **Une mise à jour est disponible** → *Télécharger* ou *Plus tard* ;
2. **Téléchargement** → *Annuler* reste possible à tout moment ;
3. **Mise à jour prête** → *Redémarrer et installer* ou *Annuler*.

La recherche a lieu quelques secondes après le démarrage, et à la demande
depuis la page *Nouveautés*. Elle se désactive dans *Paramètres →
Rechercher les mises à jour au démarrage*.

### Ce qui est vérifié

- la requête part uniquement vers `api.github.com`, en HTTPS ;
- seules les adresses des domaines de GitHub sont acceptées au téléchargement,
  y compris après redirection ;
- la taille du fichier reçu est comparée à celle annoncée ;
- le fichier est écrit dans le cache de l'application, nulle part ailleurs ;
- l'installateur n'est jamais lancé automatiquement.

**Aucune donnée n'est transmise** : la requête ne contient ni identifiant, ni
adresse de courriel, ni information sur votre bibliothèque. Elle se limite à
demander la dernière version publiée.


## Utilisation

### Premiers pas

1. **Bibliothèque** → *Importer des fichiers* (ou glissez vos fichiers dans la
   fenêtre). Le logiciel demande si vous voulez **référencer** vos fichiers
   (aucune copie, recommandé) ou les **copier** dans la bibliothèque.
2. Cliquez sur une vignette pour la sélectionner, **double-cliquez** pour
   l'appliquer immédiatement.
3. **Horaires** → *Créer un programme jour / nuit* pour une mise en place en
   deux clics.

### Lignes de commande

| Commande | Effet |
|---|---|
| `WallpaperStudio.exe` | Lance l'application |
| `WallpaperStudio.exe --minimise` | Démarre dans la zone de notification |
| `WallpaperStudio.exe --selftest` | Vérifie l'environnement et quitte |
| `WallpaperStudio.exe --diagnostic` | Vérifie que le fond s'affiche vraiment (réduit brièvement les fenêtres, puis les restaure) |
| `WallpaperStudio.exe --debug` | Journalisation détaillée |

### Zone de notification

Fermer la fenêtre **n'arrête pas** le logiciel : les fonds restent affichés et
le planificateur continue. Le menu de l'icône permet d'ouvrir l'interface, de
mettre en pause, de suspendre la planification et de quitter réellement.

---

## Configuration des horaires

### Principe

Une règle associe **un fond**, **une plage horaire**, **des jours** et
éventuellement **un écran**.

L'intervalle est fermé à gauche et ouvert à droite : `[début, fin[`. Deux règles
08h00–22h00 et 22h00–08h00 se succèdent donc sans trou ni recouvrement.

### Plages traversant minuit

Si l'heure de fin précède l'heure de début, la plage traverse minuit. **Les
jours cochés désignent le jour où la plage commence.**

> Une règle 22h00–08h00 cochée « lundi » couvre le lundi de 22h00 jusqu'au mardi
> 08h00.

### Exemple de programmation

| Horaire | Écran 1 | Écran 2 |
|---|---|---|
| 08h–12h | Paysage animé | Image JPG |
| 12h–18h | Vidéo MP4 | GIF animé |
| 18h–22h | Paysage du soir | Vidéo MP4 |
| 22h–08h | Fond nocturne | Image PNG |

Créez huit règles, quatre avec « Écran 1 » et quatre avec « Écran 2 ».

### Conflits

Quand plusieurs règles s'appliquent au même instant, la politique choisie dans
la page Horaires tranche :

- **Priorité la plus élevée** (par défaut) ;
- **Règle commencée le plus récemment** ;
- **Règle la plus ancienne** ;
- **Plage la plus courte** — pratique pour glisser une exception ponctuelle dans
  une plage large.

À rang égal, une règle visant explicitement un écran l'emporte toujours sur une
règle « tous les écrans ».

### Fiabilité

Le planificateur **compare des états** au lieu de suivre un compte à rebours :
à chaque réveil il recalcule le fond attendu pour chaque écran et ne change que
ce qui diffère. Conséquences :

- une transition manquée pendant une mise en veille est rattrapée au réveil ;
- un changement d'heure système ou une correction NTP est absorbé ;
- un fond déjà affiché n'est jamais réappliqué, donc aucun clignotement ;
- le planificateur se relance tout seul et une seule boucle peut exister.

Le mode **manuel** (case « Planification automatique » décochée) suspend les
règles, et *Suspendre 1 h* les met en pause temporairement.

---

## Gestion des écrans

La page **Écrans** affiche un schéma à l'échelle de votre bureau virtuel.
Cliquez sur un écran pour le configurer : cadrage, volume, vitesse, pause,
retour au fond précédent, ou exclusion de la gestion automatique.

Trois modes globaux :

- **Un fond différent par écran** (par défaut) ;
- **Le même fond sur tous les écrans** ;
- **Image panoramique répartie** (images fixes uniquement).

### Débranchement et rebranchement

Chaque écran est identifié par une **clé matérielle stable** dérivée de son
identifiant PnP, et non par son nom `\\.\DISPLAY1`, qui change. Débrancher puis
rebrancher un écran restaure donc sa configuration, **sans toucher à celle des
autres écrans**.

---

## Fonds d'écran web

Un fond web est un dossier contenant `index.html`, et éventuellement un
manifeste `wallpaper.json` :

```json
{
  "nom": "Horloge Wallpaper Studio",
  "auteur": "Vous",
  "description": "Horloge et particules",
  "version": "1.0",
  "reseau": false
}
```

Un exemple complet est fourni dans `resources/web/horloge/` : horloge, date du
jour en français, particules animées et halo suivant le curseur.

### Bac à sable

Un fond web est du **code tiers**, exécuté avec des privilèges réduits :

- profil éphémère : ni cookies, ni cache, ni stockage local conservés ;
- **accès réseau refusé par défaut** — il faut `"reseau": true` dans le
  manifeste ;
- aucun accès aux fichiers hors de son propre dossier ;
- caméra, micro, géolocalisation, notifications et presse-papiers refusés ;
- pas de pont JavaScript vers l'application.

L'application expose uniquement un objet `window.wallpaperStudio` en lecture seule et émet
un événement `wps-souris` avec la position du curseur.

### Coût

QtWebEngine (Chromium) consomme 120 à 250 Mo de mémoire par fond web actif,
nettement plus qu'une image ou une vidéo.

---

## Formats pris en charge

Les listes ci-dessous correspondent à des moteurs **réellement implémentés**.

### Images fixes — moteur Qt + Pillow

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.tif` `.tiff` `.ico` `.jfif`

La transparence PNG/WEBP est respectée (composition sur fond noir).

### Images animées — décodage Pillow, affichage Qt

`.gif` · `.png` (APNG) · `.webp` animé

Toutes les images sont décodées **une seule fois** au chargement, corrections
comprises : la lecture ne coûte ensuite qu'une recopie. Si l'animation dépasse
le budget mémoire, le logiciel bascule sur un décodage à la volée, sans
corrections colorimétriques.

### Vidéos — moteur libVLC

`.mp4` `.m4v` `.mkv` `.webm` `.mov` `.avi` `.wmv` `.flv` `.mpg` `.mpeg`
`.m2ts` `.ts` `.ogv` `.3gp` `.asf`

La couverture réelle dépend des décodeurs embarqués dans votre libVLC. Un
fichier illisible est **signalé explicitement** plutôt que de laisser un écran
noir : fichier introuvable, fichier vide, flux illisible, ou absence d'image
vidéo.

### Fonds web — QtWebEngine

Dossier contenant `index.html`, ou fichier `.html`.

---

## Performances

Cible : Intel Core i3-10110U, 8 Go de RAM, Intel UHD Graphics.

### Mises en pause automatiques

| Condition | Activée par défaut |
|---|---|
| Application en plein écran (jeu, vidéo) | oui |
| Fenêtre maximisée | non |
| Fonctionnement sur batterie | oui |
| Session verrouillée | oui |

### Profils

| Profil | Plafond FPS |
|---|---|
| Économie d'énergie | 20 |
| Équilibre (défaut) | 30 |
| Qualité | 60 |

### Mesures affichées

RAM du processus, charge CPU de l'application et du système, FPS par écran,
nombre de fonds actifs et animés, état d'alimentation.

La **charge GPU n'est pas mesurée** : aucune API Windows ne la fournit sans
bibliothèque constructeur. La page l'indique clairement.

### Frugalité : ce que fait le logiciel pour s'effacer

Le logiciel est conçu pour tourner toute la journée sur une machine à 8 Go.
Quatre mécanismes y contribuent :

1. **Interface construite à la demande.** Les huit pages ne sont pas créées au
   démarrage : chacune naît à sa première ouverture. Lancé en arrière-plan
   (`--minimise`), le logiciel ne construit **aucune** interface.
2. **Interface libérée quand elle ne sert plus.** 45 secondes après la
   fermeture de la fenêtre, l'interface est détruite et la mémoire rendue à
   Windows. La fenêtre se reconstruit à la réouverture. Réglage
   *« Libérer la mémoire de l'interface quand la fenêtre est fermée »*.
3. **libVLC libérée sans vidéo.** Le lecteur vidéo occupe ~85 Mo. Dès qu'aucun
   écran n'affiche de vidéo, il est déchargé au bout de 20 secondes, et
   rechargé à la vidéo suivante. Un compteur d'utilisation garantit qu'il
   n'est jamais libéré pendant une lecture.
4. **Minuteurs arrêtés quand rien n'est visible.** Fenêtre masquée, les
   rafraîchissements de l'interface s'arrêtent, le relevé psutil cesse et la
   surveillance des conditions de pause passe de 2 à 5 secondes.

À cela s'ajoutent des réglages libVLC économes : tampon d'entrée réduit à
300 ms, deux fils de décodage au maximum, et **aucune sortie audio ouverte**
quand le fond est muet.

> La restitution de mémoire utilise `SetProcessWorkingSetSize`. Les pages
> réellement inutilisées repartent vers la liste des pages libres ; celles dont
> le logiciel aurait de nouveau besoin sont rechargées à la demande. La mémoire
> redevient donc disponible pour vos autres applications.

### Consommation mesurée

Mesures prises sur la machine cible (i3-10110U, 8 Go, écran 1760×990), avec
l'exécutable compilé.

| Situation | RAM | CPU | Fils |
|---|---|---|---|
| Arrière-plan, aucune interface | 68 Mo | 0 % | 10 |
| Fenêtre ouverte | 135 Mo | 3 % | 10 |
| Fenêtre fermée, après libération automatique | **7 Mo** | 0 % | 6 |
| Arrière-plan + fond image fixe | 26 Mo | ~1 % | 18 |
| Arrière-plan + vidéo 720p | 156 Mo | ~4,5 % | 18 |

Pour comparaison, la version 0.1.1 consommait 144 Mo au repos avec l'interface
systématiquement construite, et 5,5 % de processeur fenêtre masquée.

**Le cas le plus économe** est un fond image fixe : une fois l'image décodée,
le rendu ne coûte plus rien et le processeur retombe sous 1 %.

---

## Compilation

```bat
.venv\Scripts\python.exe scripts\build.py --clean
```

Options :

| Option | Effet |
|---|---|
| `--onefile` | Un seul `.exe` (démarrage plus lent) |
| `--with-vlc` | Embarque libVLC : plus besoin de VLC installé |
| `--no-web` | Retire QtWebEngine : paquet ~300 Mo plus léger, sans fonds web |
| `--clean` | Vide `dist/` et `build/` au préalable |

Le script génère l'icône `.ico` à partir du dessin vectoriel de l'application,
puis allège le paquet en supprimant les ressources de débogage de QtWebEngine
(environ 126 Mo).

Taille obtenue : **454 Mo** en version complète (QtWebEngine en représente
l'essentiel), environ 160 Mo avec `--no-web`.

### Vérifier le résultat

```bat
dist\WallpaperStudio\WallpaperStudio.exe --selftest
```

### Version installable

Non fournie. Le dossier produit étant autonome, un installeur se crée
facilement avec [Inno Setup](https://jrsoftware.org/isinfo.php) en pointant sur
`dist\WallpaperStudio`. Pensez alors à supprimer `portable.txt` pour que
les données aillent dans `%LOCALAPPDATA%`.

---

## Tests

```bat
.venv\Scripts\python.exe -m pytest tests\ -v
```

**131 tests**, répartis ainsi :

| Fichier | Tests | Couvre |
|---|---|---|
| `test_scheduler_rules.py` | 45 | Plages horaires, minuit, jours, conflits, transitions |
| `test_engine.py` | 34 | Écrans, cadrages, rendu, erreurs de lecture, mémoire |
| `test_persistence.py` | 22 | Réglages, bibliothèque, redémarrage, sauvegarde |
| `test_scheduler_service.py` | 16 | Service de planification, veille, multi-écrans |
| `test_controller.py` | 14 | Intégration, restauration, fermeture de fenêtre |

Les tests du planificateur utilisent une **horloge simulée** : une journée
entière de transitions est vérifiée en quelques millisecondes.

Les tests qui ont besoin de FFmpeg ou de libVLC sont **ignorés** proprement si
ces composants sont absents, au lieu d'échouer.

---

## Emplacement des fichiers

Installation classique :

| Contenu | Chemin |
|---|---|
| Données | `%LOCALAPPDATA%\WallpaperStudio` |
| Base de données | `…\wallpaper-studio.db` |
| Réglages | `…\config\settings.json` |
| Journaux | `…\logs\wallpaper-studio.log` |
| Vignettes | `…\thumbnails\` |
| Fonds web installés | `…\web\` |

En mode portable, remplacez `%LOCALAPPDATA%\WallpaperStudio` par le
sous-dossier `data\` de l'application.

Le démarrage automatique utilise
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, sans privilège
administrateur.

---

## Résolution des problèmes

### Je ne vois pas mon fond d'écran

Lancez d'abord le diagnostic, qui tranche en quelques secondes :

```bat
WallpaperStudio.exe --diagnostic
```

Il affiche une mire colorée sur le bureau, réduit les fenêtres, capture
l'écran, les restaure, puis indique si la mire a été détectée et, sinon,
pourquoi.

- **Un autre logiciel de fond d'écran tourne.** Wallpaper Engine et Lively
  occupent la même couche Windows. La page d'accueil vous en avertit : fermez
  l'autre logiciel.
- **Fenêtres au premier plan.** Réduisez toutes les fenêtres (`Win + D`).
- **Pause automatique active.** Consultez la page Performances : le motif de la
  pause y est affiché.

### Les vidéos ne se lancent pas

Vérifiez la ligne `libVLC` dans `--selftest`. Installez VLC **64 bits**, ou
recompilez avec `--with-vlc`. Une version 32 bits de VLC ne peut pas être
chargée par une application 64 bits.

### Les icônes du bureau scintillent

Windows n'a pas fourni de couche `WorkerW` et l'application utilise `Progman`
en repli. La page d'accueil le signale. Redémarrer l'Explorateur Windows
suffit généralement.

### Mon fond disparaît après un redémarrage de l'Explorateur

L'application le détecte dans les cinq secondes et rattache ses fenêtres. Un
message le confirme.

### La transition horaire n'a pas eu lieu

- Vérifiez que « Planification automatique » est cochée et que la règle est
  active.
- Vérifiez les **jours cochés** : pour une règle de nuit, c'est le jour du
  *début* qui compte.
- La page Horaires affiche l'heure de la prochaine transition et la page
  Historique liste tous les changements effectués.

### Un fichier est marqué « introuvable »

Vous avez importé en mode « référencer » et le fichier a été déplacé. Utilisez
*Vérifier les fichiers* dans la bibliothèque, puis réimportez-le.

---

## Architecture

```
WallpaperStudio/
├── main.py                      point d'entrée, instance unique, --selftest
├── requirements.txt
├── README.md  CHANGELOG.md  LICENSES.md
├── wallpaper_studio/
│   ├── app.py                   contrôleur : relie tous les sous-systèmes
│   ├── app_paths.py             emplacements, mode portable
│   ├── i18n.py                  traduction (français = langue source)
│   ├── logging_setup.py
│   ├── system/                  intégration Windows
│   │   ├── win_desktop.py       couche WorkerW, DPI, rattachement
│   │   ├── monitors.py          énumération, clé matérielle stable
│   │   ├── foreground.py        détection plein écran / maximisé
│   │   ├── power.py             batterie, session verrouillée
│   │   ├── mouse.py             suivi global du curseur
│   │   └── autostart.py         démarrage avec Windows
│   ├── data/                    base SQLite, modèles, dépôts, réglages
│   ├── media/                   analyse, vignettes, traitements, conversion
│   ├── engine/
│   │   ├── wallpaper_engine.py  orchestrateur
│   │   ├── surface.py           fenêtre de fond, une par écran
│   │   ├── effects.py           8 effets de particules
│   │   └── backends/            image, vidéo (libVLC), web (QtWebEngine)
│   ├── scheduler/
│   │   ├── rules.py             logique pure, testable, sans effet de bord
│   │   └── scheduler.py         service en arrière-plan
│   ├── perf/                    mesures et économies de ressources
│   └── ui/                      interface PySide6
├── resources/                   icônes, fonds web, traductions
├── tests/                       131 tests
└── scripts/build.py             construction de l'exécutable
```

### Comment le fond est affiché

L'Explorateur Windows dessine le bureau. Pour placer un contenu **derrière les
icônes**, la technique consiste à reparenter une fenêtre dans une fenêtre de
classe `WorkerW` appartenant à l'Explorateur. Il n'existe **aucune API publique**
pour cela : on envoie un message non documenté (`0x052C`) à `Progman`, qui crée
la couche.

Trois agencements sont pris en charge, choisis automatiquement au démarrage :

- **Windows 10 et Windows 11 anciens** (`sibling_workerw`) : `SHELLDLL_DefView`
  est enfant d'une `WorkerW` de premier niveau, et une **seconde** `WorkerW`
  sœur sert de support. Le fond s'affiche **derrière les icônes**.
- **Windows 11 intermédiaires** (`progman_child_workerw`) : `SHELLDLL_DefView`
  est directement enfant de `Progman`, et une `WorkerW` enfant de `Progman` se
  place sous les icônes. Le fond s'affiche **derrière les icônes**.
- **Windows 11 24H2 et suivants** : même agencement, mais `Progman` est passé
  à DirectComposition. Voir ci-dessous — le fond reste **derrière les icônes**.

### Le cas de Windows 11 24H2 et suivants

À partir de cette version, `Progman` porte le style
`WS_EX_NOREDIRECTIONBITMAP` : il dessine via **DirectComposition** et n'a plus
de surface de redirection DWM. Conséquence mesurée sur un build 26200 : une
fenêtre GDI ordinaire placée dans sa `WorkerW` est bien créée, se déclare
visible, occupe la bonne position dans l'ordre Z — et **n'est jamais dessinée
à l'écran**. Beaucoup de logiciels de fond d'écran s'y cassent les dents.

La solution retenue tient en un style : **`WS_EX_LAYERED`**. Les fenêtres en
couche empruntent un autre chemin de composition dans DWM, qui lui fonctionne.
C'est d'ailleurs ainsi que l'Explorateur affiche `SHELLDLL_DefView`, lui aussi
en couche. Concrètement, la fenêtre de fond reçoit :

```
WS_EX_LAYERED  +  SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
```

L'alpha vaut 255, donc la fenêtre reste parfaitement opaque : on ne cherche pas
de transparence, seulement le bon chemin de composition. Le fond s'affiche
alors **sous les icônes du bureau**, y compris pour la vidéo, dont libVLC
dessine le rendu dans une fenêtre enfant.

Ce point est vérifiable à tout moment avec `--diagnostic`, qui affiche une mire
sur le bureau et contrôle que les icônes restent visibles.

Si aucune couche n'est exploitable, l'application se rabat sur `Progman` :
le rendu fonctionne mais les icônes peuvent scintiller.

### Limites assumées de cette approche

- `0x052C` n'est pas documenté par Microsoft et peut cesser de fonctionner lors
  d'une mise à jour de Windows. Le repli sur `Progman` garantit alors un
  affichage dégradé mais fonctionnel.
- Un redémarrage d'`explorer.exe` détruit la couche : l'application surveille
  et rattache ses fenêtres.
- **Les clics de souris ne parviennent pas** aux fenêtres de fond : Windows les
  envoie à `SHELLDLL_DefView`, qui est au-dessus. Seule la position du curseur
  est transmise, par interrogation périodique.
- Deux gestionnaires de fonds d'écran se superposent s'ils tournent ensemble.

### Choix techniques

| Choix | Raison |
|---|---|
| **Python 3.11** | PySide6 6.12 ne publie pas encore de roue pour Python 3.14 |
| **PySide6** (LGPL) | Interface native, licence compatible, rendu Qt éprouvé |
| **libVLC** pour la vidéo | Rend directement dans un `HWND` : aucune recopie d'image vers Python, décodage matériel, couverture de formats très large |
| **Pillow** pour les images | Gère APNG et WEBP animé, dont Qt ne décode pas toutes les variantes |
| **SQLite** | Sans serveur, mode WAL pour les écritures concurrentes du planificateur |
| **Décodage unique des animations** | Supprime tout traitement pendant la lecture, au prix d'un peu de mémoire bornée |
| **Horloge injectable** | Rend le planificateur testable sans attendre des heures |

---

## Dépendances et licences

Voir [LICENSES.md](LICENSES.md) pour le détail complet.

| Composant | Licence | Usage |
|---|---|---|
| PySide6 / Qt 6 | LGPL v3 | Interface, rendu, QtWebEngine |
| libVLC | LGPL v2.1+ | Lecture vidéo (lien dynamique) |
| Pillow | MIT-CMU | Traitement d'images |
| psutil | BSD 3-clauses | Mesures de performance |
| python-vlc | LGPL v2.1+ | Liaison Python vers libVLC |
| FFmpeg | LGPL v2.1+ ou GPL v2+ | Facultatif : vignettes, métadonnées, conversion |

Ce logiciel est une création originale. Il s'inspire des **fonctionnalités**
proposées par les gestionnaires de fonds d'écran existants, sans réutiliser
leur code, leurs ressources ni leurs formats propriétaires.
