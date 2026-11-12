# Construction Windows

## Prérequis

- Windows 11 x64 et Windows PowerShell 5.1 ou PowerShell 7.
- Compilateur C# du .NET Framework x64 sous WINDIR, avec Windows Forms, System.IO.Compression et Microsoft.CSharp.
- Python 3.14.4 x64 comme interpréteur de construction. Le Python embarquable officiel extrait dans un dossier de travail convient.
- Deux archives Windows x64 officielles, Python embarquable et Node.js, aux URL et SHA-256 de runtimes.lock.json. Télécharger les archives dans un répertoire de travail hors Git.
- Accès au registre npm officiel et au CDN Playwright pendant la préparation. Chrome local est nécessaire à la recette S4-UI. Le moteur PDF livré utilise le Chromium Headless Shell privé.

## Commande unique

Depuis PowerShell, adapter les quatre chemins. La destination doit être nouvelle. Le script peut être appelé depuis un autre répertoire.

```powershell
& 'C:\chemin\gary\S4B\construire_livraison.ps1' `
  -Python 'C:\travail\python-build\python.exe' `
  -PythonZip 'C:\travail\python-3.14.4-embed-amd64.zip' `
  -NodeZip 'C:\travail\node-v24.22.1-win-x64.zip' `
  -Output 'C:\travail\Gary_V5'
```

Le script vérifie les prérequis, les SHA-256 des archives et des sources applicatives, puis installe les paquets avec npm ci à partir de package-lock.json. Il construit le frontend, prépare Chromium via la version verrouillée de Playwright, rejoue la recette S4-UI et écarte les dépendances de développement du paquet. Le ZIP contient le runtime d'application et une copie du runtime Python de maintenance. Le compilateur produit le désinstallateur puis embarque celui-ci et le ZIP dans l'installateur. Le script compare les empreintes des ressources embarquées et écrit SHA256SUMS.txt.

Les seules sorties destinées à la qualification sont Installer_Gary.exe, Gary_V5_Portable.zip et SHA256SUMS.txt. Exclure du dépôt les archives de dépendances, les dossiers de travail et les binaires générés. Le ZIP et le PE peuvent avoir des empreintes différentes de S4B, notamment à cause des runtimes, de la résolution des transitives et des métadonnées de compilation. La construction ne lance ni installation ni désinstallation.

## Vérification des entrées

Le SHA-256 de Node a été comparé au manifeste SHASUMS256.txt de sa distribution officielle. Le SHA-256 Python fixe les octets téléchargés de python.org et la signature Authenticode de python.exe a été vérifiée sur l'entrée de qualification. Le verrou npm fixe les versions, les URL de tarballs et leur intégrité. Le navigateur est récupéré par le programme d'installation Playwright verrouillé. Le verrou fixe aussi les SHA-256 de tous les fichiers navigateur et auxiliaires observés lors de la récupération officielle, hors journaux et métadonnées locales .links et DEPENDENCIES_VALIDATED. Ces empreintes dérivent des fichiers téléchargés et ne constituent pas une signature indépendante du CDN.

Voir [Dépendances et notices](DEPENDANCES.md) pour les droits et conditions de distribution.


