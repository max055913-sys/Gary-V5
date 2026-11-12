# Installation autonome de Gary V5

## Code source et construction

L’ancien environnement de développement utilisait `v5/.venv`, des dépendances locales et `v5/data`. Pour reconstruire la distribution actuelle depuis les sources, suivre le [guide de construction Windows](../../../docs/CONSTRUCTION_WINDOWS.md). La procédure utilise des archives Python et Node officielles vérifiées, le verrou npm et le compilateur Windows. Elle produit un installateur et un ZIP portable séparés.

## Installation distribuée

Sous Windows 11 x64, lancer `Installer_Gary.exe` pour installer Gary pour le compte Windows courant. Le raccourci Gary ouvre l’interface locale. L’archive portable permet d’utiliser le paquet décompressé en lançant `Gary.pyw` avec le Python privé de `MaintenanceRuntime`.

Dans le dossier d’installation ou d’extraction :

- `App/` contient l’application. `App/v5/runtime/python/` et `App/v5/runtime/node/` fournissent les runtimes privés. L’export PDF utilise le Chromium Headless Shell de `App/v5/runtime/browser/`.
- `Data/`, à côté de `App/`, contient les données locales, dont les réglages, bases, caches, fiches et le coffre DPAPI.
- `MaintenanceRuntime/` contient le Python privé utilisé pour le lancement et la maintenance.

La case **Démarrer Gary automatiquement avec Windows** lance le serveur en arrière-plan à l’ouverture de session. Le raccourci Gary ouvre l’interface. Les actions **Arrêter Gary** et **Redémarrer Gary** se trouvent dans **Configuration et sauvegardes**. Terminer ou annuler une génération active avant un redémarrage.

## Accès API et PDF patient

Enregistrer sa propre clé OpenAI dans **Configuration et sauvegardes → Connexion OpenAI**, puis activer l’accès selon le budget choisi. La clé est protégée par DPAPI pour le compte Windows courant. Une réponse CR admissible peut éviter un nouvel appel Sol. Le contrôle de santé local indique la configuration sans interroger le fournisseur.

L’export PDF exige l’approbation de la version patient. Le paquet distribué utilise ses dépendances privées. Pour une configuration spécifique, `GARY_PDF_NODE`, `GARY_PDF_PLAYWRIGHT` et `GARY_PDF_BROWSER` permettent de fournir des chemins de remplacement.

## Sauvegarde et désinstallation

Arrêter Gary proprement avant de sauvegarder le dossier **Data** en entier. Protéger la sauvegarde comme les données d’origine. Pour une restauration sur un autre poste ou sous un autre compte, la clé API protégée par DPAPI peut nécessiter une nouvelle saisie. Ne jamais exporter la clé en clair.

Pour une installation enregistrée, utiliser **Paramètres Windows → Applications → Applications installées → Gary → Désinstaller**. Le désinstallateur natif propose de conserver `Data` par défaut. La suppression complète de `Data` demande une confirmation distincte. Une réinstallation dans le même emplacement peut reprendre les données conservées. Sauvegarder avant toute suppression complète.
