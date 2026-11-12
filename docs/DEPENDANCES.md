# Dépendances et notices

| Composant | Version de référence | Licence ou état |
| --- | --- | --- |
| Python embarquable officiel x64 | 3.14.4 | Licence Python incluse. Backend sans paquet PyPI. Examiner les notices des modules et DLL redistribués. |
| Node officiel x64 et npm de construction | 24.22.1 et 11.19.1 | Notice Node incluse au runtime. npm reste un outil de construction. |
| React, React DOM | 19.3.1 | MIT. Le verrou fixe aussi scheduler et les transitives. |
| Vite | 7.3.7 | MIT. Dépendance de build. |
| esbuild | 0.28.2 | MIT. Le verrou couvre le paquet natif Windows x64. |
| Playwright et Playwright Core | 1.62.1 | Apache-2.0. Notices présentes dans les packages. |
| Chromium Headless Shell, FFmpeg, winldd | 1234, 1011, 1007 | Téléchargements Playwright. Inventaire détaillé des licences et notices binaires à compléter avant redistribution. |
| DLL VC Runtime | Livrées avec Python officiel | Conditions Microsoft à vérifier avant redistribution. |
| .NET Framework et csc.exe | Chemin système v4.0.30319 | Outils du poste de compilation, exclus du dépôt. |

Le moteur PDF utilise Node, esbuild, React et Playwright avec Chromium Headless Shell. Le runtime de maintenance emploie Python embarquable, GaryUpdate.pyw et maintenance_transaction.py. Le désinstallateur natif est compilé à partir d'Installer.cs.

Le logo est une création originale selon le propriétaire. L'ICO embarque une version redimensionnée du même visuel. Aucun fichier de licence Gary n'est ajouté.
