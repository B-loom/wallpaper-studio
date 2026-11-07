# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
projet applique le [versionnage sémantique](https://semver.org/lang/fr/).

## [0.1.0] - 2026-10-19

Première version fonctionnelle.

### Ajouté

#### Moteur de fonds d'écran
- Rendu derrière les icônes du bureau via la couche `WorkerW` de l'Explorateur.
- Prise en charge des deux agencements Windows : `WorkerW` sœur (Windows 10 et
  Windows 11 anciens) et `WorkerW` enfant de `Progman` (Windows 11 24H2+).
- Repli automatique sur `Progman` quand aucune `WorkerW` n'est exploitable.
- Détection et rattachement automatique après un redémarrage de l'Explorateur.
- Conscience du DPI par moniteur, pour un alignement exact sur chaque écran.
- Détection des gestionnaires de fonds d'écran concurrents, avec avertissement.

#### Types de contenus
- Images fixes : JPG, PNG, BMP, WEBP, TIFF, ICO, JFIF.
- Images animées : GIF, APNG, WEBP animé, avec décodage unique au chargement et
  repli sur un décodage à la volée si le budget mémoire est dépassé.
- Vidéos via libVLC : MP4, MKV, WEBM, MOV, AVI, WMV, FLV, MPG, TS et autres.
- Fonds d'écran web HTML/CSS/JavaScript exécutés dans un bac à sable.
- Cinq modes de cadrage : remplir, ajuster, étirer, centrer, mosaïque.

#### Planificateur horaire
- Règles associant un fond, une plage horaire, des jours et un écran.
- Gestion correcte des plages traversant minuit, le masque de jours désignant
  le jour de début de plage.
- Quatre politiques de résolution des conflits ; une règle ciblant un écran
  l'emporte sur une règle globale.
- Comparaison d'états plutôt que compte à rebours : rattrapage après veille,
  résistance aux changements d'heure, aucune réapplication inutile.
- Fonctionnement en arrière-plan, instance unique garantie.
- Assistant de création d'un programme jour / nuit en deux clics.
- Mode manuel et suspension temporaire.

#### Multi-écrans
- Détection des moniteurs avec clé matérielle stable, résistante au
  rebranchement.
- Schéma interactif respectant positions et proportions réelles.
- Réglages indépendants par écran : cadrage, volume, vitesse, pause, activation.
- Modes : un fond par écran, même fond partout, image panoramique répartie.
- Restauration de la configuration d'un écran rebranché sans toucher aux autres.

#### Bibliothèque
- Import de fichiers, de dossiers entiers et par glisser-déposer.
- Choix entre référencement des fichiers d'origine et copie dans la
  bibliothèque ; aucune copie imposée.
- Tags, collections, favoris, recherche, filtres par type et sept critères de tri.
- Vignettes générées pour les images, les animations et les vidéos.
- Détection des fichiers manquants et retrait sans suppression du fichier source.

#### Éditeur
- Luminosité, contraste, saturation, teinte, flou, rotation, miroirs.
- Aperçu en temps réel avec recalcul différé.
- Presets enregistrables et réutilisables.
- Les fichiers d'origine ne sont jamais modifiés.

#### Effets visuels
- Huit effets réellement dessinés : particules, pluie, neige, étoiles,
  brouillard, lueurs, ondes, halo suivant le curseur.
- Intensité réglable par effet, budget global de particules borné.

#### Performances
- Pause automatique : plein écran, fenêtre maximisée, batterie, session
  verrouillée.
- Trois profils de qualité et plafond d'images par seconde réglable.
- Décodage matériel activable, application à chaud.
- Mesures de RAM, de charge processeur et de cadence, avec courbes.
- La charge GPU est annoncée comme non mesurée plutôt qu'estimée.

#### Intégration Windows
- Icône et menu dans la zone de notification.
- Fermeture de la fenêtre sans arrêt du moteur ni du planificateur.
- Démarrage automatique avec Windows, sans privilège administrateur.
- Mise à jour de la commande de démarrage si l'application est déplacée.

#### Conversion (module facultatif)
- Vidéo vers GIF avec palette dédiée en deux passes.
- GIF vers séquence d'images, séquence d'images vers vidéo.
- Extraction d'une image, conversion d'images, réencodage H.264.
- Jamais imposée lorsqu'un fichier est directement lisible.

#### Divers
- Interface en français, architecture de traduction par catalogues JSON.
- Thèmes sombre et clair, jeu d'icônes vectorielles original.
- Historique complet des changements de fond.
- Sauvegarde et restauration des réglages et de la base de données.
- Mode portable détecté par la présence de `portable.txt`.
- Vérification de l'environnement par `--selftest`.
- Script de construction PyInstaller avec allègement du paquet.
- 131 tests automatisés, dont le planificateur piloté par horloge simulée.

### Problèmes connus
- Le mode panoramique ne gère que les images fixes.
- Les clics de souris ne parviennent pas aux fonds d'écran : limite de Windows,
  seule la position du curseur est transmise.
- La réaction au son, l'effet de parallaxe et l'éditeur de scènes ne sont pas
  implémentés.
- Aucun programme d'installation n'est fourni : seule la version portable l'est.

## [0.1.1] - 2026-10-20

### Corrige

- **Le fond d'ecran ne s'affichait pas sur Windows 11 24H2 et suivants.**
  `Progman` y porte desormais `WS_EX_NOREDIRECTIONBITMAP` : il dessine via
  DirectComposition et n'a plus de surface de redirection DWM. Une fenetre
  placee dans sa couche `WorkerW` etait donc creee, declaree visible et
  correctement positionnee, mais jamais dessinee a l'ecran. L'application
  detecte maintenant ce style au demarrage et bascule sur `SHELLDLL_DefView`,
  qui reste composee par DWM. Sur ces versions, le fond recouvre les icones du
  bureau : la limite est documentee et signalee dans l'interface.
- Les styles de fenetre sont appliques **apres** le reparentage, et
  `SWP_FRAMECHANGED` est desormais transmis : sans lui, Windows conservait le
  cadre calcule avant le changement de styles.
- La version de libVLC affichee sur la page d'accueil et dans les parametres
  indiquait « absente » tant qu'aucune video n'avait ete lue, le chargement
  etant differe. Une fonction dediee force desormais le chargement avant
  l'affichage.

### Ajoute

- Commande `--diagnostic` : affiche une mire sur le bureau, reduit les
  fenetres, capture l'ecran, les restaure, puis indique si le fond est
  reellement visible et, sinon, la cause probable.
- Detection explicite de la couche utilisable (`workerw_layer_usable()`) au
  lieu d'un essai silencieux.

### Supprime

- Cinq reglages sans effet reel (`transition_fondu`, `duree_transition_ms`,
  `fps_reduit_en_economie`, `muet_global` et `journal_detaille` inutilises,
  `demarrer_avec_windows` redondant avec le registre). Les deux derniers ont
  ete reellement implementes plutot que retires.

## [0.2.0] - 2026-10-21

Version consacree a la frugalite : moins de memoire, moins de processeur.

### Modifie

- **L'interface est construite a la demande.** Les huit pages etaient creees au
  demarrage (78 Mo) alors que l'utilisateur n'en consulte souvent que deux ou
  trois. Chaque page nait desormais a sa premiere ouverture.
- **Aucune interface en mode arriere-plan.** Lance avec `--minimise`, le
  logiciel ne construit plus du tout la fenetre principale : 68 Mo au lieu
  de 144 Mo.
- **L'interface est liberee 45 s apres la fermeture de la fenetre**, et la
  memoire rendue a Windows. Mesure sur l'executable : 135 Mo -> 7 Mo. La
  fenetre se reconstruit a la reouverture. Reglage dedie dans les parametres.
- **libVLC est liberee quand plus aucune video n'est affichee** (environ 85 Mo),
  apres 20 s d'inactivite, et rechargee a la video suivante.
- **Les minuteurs s'arretent quand la fenetre est masquee.** Le processeur
  passe de 5,5 % a 0 % en arriere-plan.
- Le releve de performances (psutil) ne tourne plus que lorsque la page
  Performances est ouverte.
- Periodes allongees la ou la reactivite n'apporte rien : accueil 2 s -> 4 s,
  planificateur 1 s -> 5 s, detection d'ecrans 4 s -> 10 s, surveillance de la
  couche de bureau 5 s -> 10 s, conditions de pause 2 s -> 5 s en arriere-plan.
- Reglages libVLC plus econome : tampon d'entree de 1 s ramene a 300 ms,
  decodage limite a deux fils, `lua` et les interactions desactives.
- **Aucune sortie audio n'est ouverte pour un fond muet**, ce qui supprime un
  fil d'execution et ses tampons.
- Nombre de fils d'execution ramene de 34 a 10 (6 une fois l'interface liberee).

### Corrige

- L'instance libVLC, partagee par toute l'application, pouvait etre liberee par
  un moteur alors qu'un autre lisait encore une video. Un compteur
  d'utilisation garantit desormais qu'elle ne l'est jamais pendant une lecture.

### Ajoute

- Module `wallpaper_studio/system/memory.py` : restitution de la memoire inutilisee au
  systeme lors des passages au repos.
- Reglage « Liberer la memoire de l'interface quand la fenetre est fermee ».
- 12 tests verrouillant ces optimisations (creation paresseuse, arret des
  minuteurs, liberation de libVLC, restitution de memoire).

## [1.0.0] - 2026-11-07

Premiere version publique. Le logiciel s'appelle desormais **Wallpaper Studio**.

### Corrige

- **Le fond d'ecran recouvrait les icones du bureau sur Windows 11 24H2+.**
  La cause etait identifiee (Progman dessine via DirectComposition), mais le
  contournement retenu jusqu'ici passait par `SHELLDLL_DefView`, au-dessus des
  icones. La vraie solution est le style `WS_EX_LAYERED` associe a
  `SetLayeredWindowAttributes(..., 255, LWA_ALPHA)` : les fenetres en couche
  empruntent un chemin de composition que DWM honore encore. Le fond est de
  nouveau dessine **sous les icones**, y compris pour la video.
- Le repli degrade sur `SHELLDLL_DefView` n'est plus necessaire ; la couche
  `WorkerW` redevient la cible sur toutes les versions de Windows.

### Modifie

- Renommage complet : « Yoyo Wallpaper Studio » devient « Wallpaper Studio ».
  Le paquet Python, l'executable, le dossier de donnees et l'identifiant de
  demarrage automatique suivent.
- Nouvelle identite visuelle « nuit etoilee » : fonds bleu nuit, accent violet
  vers cyan, cartes et champs redessines, icone de l'application refaite.
- Page d'accueil : l'etat s'affiche en tuiles plutot qu'en lignes.

### Ajoute dans la 1.0.0 (suite)

- **Choix de la langue au premier lancement** : un dialogue bilingue propose le
  francais ou l'anglais. Le choix est modifiable dans les parametres.
- **Interface anglaise complete** : catalogue de 280 entrees applique par
  parcours de l'arbre de widgets, sans toucher au code des vues. Une langue
  supplementaire s'ajoute par un simple fichier JSON.
- **Page Nouveautes** : notes de version affichees dans la langue active, avec
  un bouton de recherche de mise a jour.
- **Mise a jour depuis GitHub** : notification quand une version plus recente
  existe, telechargement avec progression et annulation possible, puis
  installation sur confirmation explicite. Adresses restreintes aux domaines
  de GitHub, taille du fichier verifiee, aucune donnee transmise.
- 35 tests supplementaires couvrant la traduction, la comparaison de versions
  et la securite des telechargements.
