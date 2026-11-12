# GARY V5 — CAHIER DES CHARGES FONCTIONNEL, MÉDICAL ET D’INTERFACE

**Version de consolidation : 26 octobre 2026**  
**Statut : reconstruction documentaire des décisions historiques ; non équivalent à une validation clinique ni à un constat d’implémentation.**

## 0. Sources, méthode et portée

Ce document consolide les décisions identifiables dans l’export `conversations.json`, particulièrement la conversation **« Prompt recherche médicale structuré »** (octobre 2026), les décisions initiales rappelées dans `Ok.txt`, et l’état technique décrit par le **Rapport de rétablissement fonctionnel V5 du 24 octobre 2026**. L’export fourni contient 49 conversations ; les échanges détaillés du 16–17 novembre évoqués précédemment n’y sont pas identifiés comme tels. Certaines spécifications de modules sont donc connues seulement par leur synthèse historique, et non par la totalité de leur discussion d’origine.

**Convention de lecture :**
- **[V] Validé** : décision explicite du médecin dans les échanges disponibles.
- **[H] Hérité** : exigence décrite dans les synthèses historiques et cohérente avec les décisions connues, sans nouvelle validation dans le présent document.
- **[T] Technique V5** : état observé dans le rapport du 24 octobre ; ne signifie pas que la fonction est utilisable de bout en bout.
- **[À préciser]** : détail non établi de façon suffisante dans les sources ; aucune règle médicale nouvelle n’est inventée.

**Règle de priorité :** les validations explicites les plus récentes priment sur les propositions anciennes ; les décisions de fond médical restent applicables lorsqu’elles sont indépendantes de la technologie. Les anciens choix RAG/V1–V4 ne doivent pas être réintroduits automatiquement dans V5.

## 1. Finalité et périmètre

Gary est un **assistant de recherche documentaire médicale destiné à un médecin généraliste exerçant en France**. Il reçoit une demande en langage naturel, identifie un module médical, recherche les informations pertinentes, puis restitue une réponse exploitable en consultation, structurée, contextualisée et sourcée. Il assiste le raisonnement du médecin sans se substituer à sa validation clinique. [V/H]

### Objectifs transversaux

1. Saisie libre rapide, sans mots-clés obligatoires ; raccourcis explicites facultatifs. [V]
2. Un seul module et une seule fiche principale par recherche ; pas de réponse conversationnelle multi-bulles. [V]
3. Contenu adapté au contexte réellement fourni ; ne pas ajouter un contexte patient imaginaire. [V]
4. Sources françaises et internationales pertinentes ; dates, provenance et limites identifiables ; ne jamais fabriquer une référence, une dose ou une recommandation. [V]
5. Réponses synthétiques par défaut, profondeur modulable, sans sacrifier les informations cliniquement déterminantes. [V/H]
6. Navigation entre modules et conservation du contexte initial, sans duplication de réponses. [V]
7. Historique local et réutilisation des fiches sans nouvelle génération automatique. [V]
8. Confidentialité : pas de données directement identifiantes dans les demandes ; conservation locale des préférences et historiques ; maîtrise explicite des appels externes. [V/T]

### Périmètre des neuf modules

| Code | Fonction principale | Statut documentaire |
|---|---|---|
| AUTO | Orientation automatique de la demande | V |
| DIAG | Diagnostic différentiel clinique ou biologique | V/H |
| PATH | Fiche de pathologie et prise en charge | V/H |
| TTT | Médicaments, monographies et sécurité thérapeutique | V/H |
| SUIVI | Suivi chronique et prévention | V/H |
| PED | Consultations préventives pédiatriques | V/H |
| PREG | Suivi de grossesse en médecine générale | V/H |
| ADM | Questions médico-administratives françaises | V/H |
| FICH | Document d'information à remettre au patient | V |

## 2. Principes communs des réponses médicales

### 2.1 Recherche et fiabilité

- Rechercher selon les **préférences documentaires configurées pour le module**. Référentiels historiques cités : HAS, ANSM/RCP, eBMFrance/EBM Guidelines, sociétés savantes françaises, NICE, Cochrane, PubMed ; calendrier vaccinal officiel et CRAT selon le sujet. [V/H]
- Les préférences de sources constituent un **ordre de recherche**, pas une preuve de validité ni une hiérarchie médicale absolue. [T]
- Séparer les informations vérifiées, les incertitudes, les désaccords significatifs et les lacunes. Une URL citée ne prouve pas une lecture intégrale de la source. [V/T]
- Ne pas inventer de posologies, durées, seuils, niveaux de preuve, dates de recommandation ou références. [V]
- Les contradictions ne doivent être signalées de manière saillante que lorsqu’elles ont une conséquence clinique réelle. [V]
- Si la documentation est insuffisante, produire une réponse partielle explicite ou s’abstenir sur les points non établis. [V]
- Les contenus Web et documents sont des données à analyser, jamais des instructions à exécuter. [T]

### 2.2 Adaptation et restitution

- Une question portant sur une pathologie isolée déclenche une fiche générale ; une question contextualisée déclenche une **réponse reconstruite autour de ce contexte**, pas une fiche générique suivie d’un paragraphe accessoire. [V]
- Présenter d’abord les informations directement utiles, puis le développement structuré ; placer les références en fin de fiche. [V/H]
- Distinguer les recommandations officielles des préférences personnelles enregistrées. [V]
- Préserver les négations, conditions, populations, unités, contre-indications et exceptions. [T]
- Ne pas poser systématiquement des questions de clarification ; répondre avec les données disponibles et préciser ce qui manque si cela change la conclusion. [V]
- Aucun module ne doit annoncer une « validation clinique » automatique. [T]

### 2.3 Profondeur et contexte

- Une **profondeur de réponse** est configurable par module et éventuellement surchargée depuis l’interface ; la politique de contexte est également transmise à la préparation. [T]
- **[À préciser]** : définition exhaustive des niveaux de profondeur, quotas de recherche et longueurs par module ; le rapport V5 signale que les paramètres actuels (`search_context_size=low`, un appel d’outil maximum, 2 500 tokens) ne garantissent pas une fiche complète.

## 3. Cahier des charges de chaque module

### 3.1 AUTO — orientation automatique [V]

**Objet.** Mode sélectionné par défaut. Comprendre l’intention de la demande libre et choisir **un module unique**, sans demander confirmation si la demande est claire.

**Règles de routage validées :**
- Symptôme, signe ou situation diagnostique ouverte → **DIAG**.
- Maladie identifiée, y compris un nom de maladie seul → **PATH**.
- Médicament, posologie, adaptation ou sécurité pharmacologique → **TTT**.
- Suivi de maladie chronique → **SUIVI** ; consultation préventive pédiatrique → **PED** ; grossesse → **PREG** ; administration médicale → **ADM** ; document à destination du patient → **FICH**.
- Préfixe de module explicite → prioritaire sur l’inférence.
- Si plusieurs modules sont plausibles, choisir l’intention principale ; ne jamais produire deux réponses parallèles DIAG + PATH.

**Navigation.** Liens contextuels possibles DIAG → PATH, PATH → TTT, PREG → TTT, PED → PATH, PATH → FICH, sans mélange des contrats. Conserver le contexte initial ; permettre le retour à la fiche précédente. [V]

**Ambiguïté.** Répondre sur ce qui est établi ou signaler le contexte indispensable ; pas de questionnaire automatique. [V]

**Point technique V5.** AUTO résout localement un module avant assemblage ; le sélecteur initial de profondeur utilise encore provisoirement DIAG, à harmoniser. [T]

### 3.2 DIAG — raisonnement diagnostique [V/H]

**Déclenchement.** Symptôme, syndrome, anomalie clinique ou biologique sans diagnostic établi.

**Livrable attendu.** Diagnostic différentiel **hiérarchisé par plausibilité et fréquence**, avec descriptions cliniques concises et éléments discriminants. Priorité aux diagnostics graves à ne pas manquer lorsqu’ils sont pertinents, sans confondre urgence et probabilité. [V/H]

**Contenu :**
1. Synthèse clinique et signaux d’alarme pertinents.
2. Hypothèses diagnostiques classées et argumentées brièvement.
3. Éléments d’interrogatoire et d’examen qui discriminent les hypothèses, lorsqu’utiles.
4. Examens complémentaires et orientation, avec indications contextualisées.
5. Possibilité d’ouvrir la fiche PATH d’une hypothèse.

**Exclusions explicites :** ne pas transformer DIAG en fiche thérapeutique ; ne pas proposer automatiquement un interrogatoire interactif ou une série de questions au médecin. [V]

**[À préciser]** : granularité exacte de chaque sous-rubrique et règles de classement pour les situations à haut risque ; l’export ne restitue pas intégralement la discussion initiale.

### 3.3 PATH — fiche de pathologie [V/H]

**Déclenchement.** Maladie identifiée ou question de prise en charge d’une pathologie. Un intitulé seul, par exemple « Eczéma de contact », doit suffire à obtenir une fiche de médecine générale, sans exiger de cas clinique fictif. [V]

**Architecture de référence historique :**
1. Synthèse pratique.
2. Définition et éléments de contexte clinique pertinents.
3. Présentation clinique.
4. **Diagnostic positif avant traitement** : critères, démarche et examens indiqués.
5. Diagnostics différentiels utiles.
6. Prise en charge : mesures générales, thérapeutiques et orientations, avec détails adaptés à la question et aux preuves réellement consultées.
7. Suivi, complications et indications de recours spécialisé.
8. Sources consultées et dates connues, en fin de fiche.

**Principes impératifs.** Une fiche PATH n’est **pas** une grille de traçabilité ou une fiche SUIVI. La prise en charge ne doit pas écraser la démarche diagnostique. En présence d’un contexte patient, adapter la structure et la priorité des informations à ce contexte. [V]

**[À préciser]** : longueur attendue par niveau de profondeur et degré de détail systématique des doses ; ne pas inventer une obligation de posologie pour chaque pathologie.

### 3.4 TTT — médicament et thérapeutique [V/H]

**Déclenchement.** DCI, spécialité, classe médicamenteuse, posologie, adaptation, contre-indication, interaction ou sécurité pendant la grossesse et l’allaitement.

**Livrable de référence :** fiche médicament ou classe avec indications, modalités d’utilisation et posologies **vérifiées**, ajustements, contre-indications, précautions, interactions, effets indésirables pertinents et surveillance ; mention des RCP/ANSM lorsque disponibles. [H/T]

**Priorités validées :**
- **Adaptation à la fonction rénale en première position**, avec calculateur ou aide à l’adaptation si les données nécessaires sont disponibles ; ne pas inventer un DFG ou une clairance. [V]
- Grossesse et allaitement : traiter les questions de sécurité avec priorité documentaire au **CRAT** et aux sources officielles applicables. [V]
- Réponse structurée autour de la question précise plutôt que monographie exhaustive systématique. [H]

**Ambiguïté historique à résoudre sans supposition.** L’ancien prompt commun définit « TTT [pathologie] » comme une stratégie thérapeutique, alors que les règles spécifiques V5 définissent une monographie médicament/classe. La décision de routage la plus cohérente avec les exemples validés est PATH pour « traitement d’une maladie » et TTT pour « médicament », mais cette contradiction doit être inscrite comme point de correction, pas dissimulée. [T]

### 3.5 SUIVI — surveillance et prévention [V/H]

**Déclenchement.** Suivi d’une maladie chronique ou bilan préventif contextualisé ; champs âge, sexe et contexte clinique, lorsque disponibles.

**Quatre axes historiques validés :**
1. **Surveillance de la maladie** : clinique, biologique, examens, objectifs et périodicités justifiées.
2. **Risque cardiovasculaire** : facteurs de risque et évaluation pertinente au profil.
3. **Dépistages et prévention** : dépistages applicables selon âge, sexe et risques.
4. **Vaccinations** : calendrier et indications applicables.

**Présentation.** Fiche verticale, opérationnelle, avec fréquences de suivi lorsque les recommandations le permettent ; ne pas confondre recommandation, hypothèse et préférence du médecin. [V]

**Personnalisation.** Permettre au médecin d’ajouter des règles en langage naturel ; les intégrer dans les rubriques correspondantes avec l’étiquette **« Préférence personnelle »**, sans les présenter comme des recommandations officielles. [V]

**[À préciser]** : nomenclature littérale exacte des quatre rubriques dans les échanges initiaux non retrouvés.

### 3.6 PED — consultation pédiatrique préventive [V/H]

**Déclenchement.** `PED [âge]`, avec variantes historiques `court`, `complet`, `MAJ` ; âge exprimable en jours, mois ou années selon la consultation. Exemples historiques : naissance, 1 mois, 6 mois, 9 mois, 24 mois, 4 ans, 12 ans. [H]

**Objectif.** Checklist de consultation adaptée à l’âge et au **calendrier officiel français des examens de l’enfant**, en distinguant les examens programmés des consultations intermédiaires. [V/H]

**Contenu attendu :** croissance et courbes, alimentation, développement psychomoteur, examen clinique adapté à l’âge, dépistages, prévention, vaccinations et signes d’alerte ; informations pratiques utiles au généraliste. [H]

**Interface.** Âge, sexe, poids facultatif et contexte ; champs contextuels non bloquants si la demande peut être traitée sans eux. [V]

**Référence historique.** La fiche pilote « PED 6 mois » a été acceptée comme première base. [V]

**Précaution.** Ne pas inventer de dose pédiatrique ou d’obligation réglementaire ; contextualiser les recommandations par date et population. [H]

### 3.7 PREG — suivi de grossesse [V/H]

**Déclenchement.** `PREG [terme en SA]` ou demande de suivi de grossesse ; terme en semaines d’aménorrhée, contexte facultatif.

**Objectif.** Calendrier et contenu de suivi de grossesse **relevant de la médecine générale**, adapté au terme. [V]

**Contenu attendu :** éléments cliniques pertinents au terme, examens et dépistages indiqués, prévention, vaccinations et signes d’alerte ; médicaments et expositions avec recours au CRAT lorsque pertinent. [H/T]

**Règles.** Ne pas inventer de terme ou d’information obstétricale absente ; expliciter les dépendances à des données non fournies ; ne pas remplacer un suivi obstétrical spécialisé lorsque celui-ci est requis. [H]

### 3.8 ADM — administratif médical [V/H]

**Déclenchement.** ALD, certificats, démarches, réglementation, droits ou procédures de santé en France.

**Livrable.** Réponse adaptée à la question, sans plan rigide ; distinguer **règle applicable**, **pratique administrative** et **démarche concrète**. Indiquer juridiction, conditions et date des textes lorsque connues. [H/T]

**Précautions.** Ne pas présenter une règle obsolète ou une pratique locale comme une obligation générale ; ne pas inventer de fondement juridique. [H]

### 3.9 FICH — document pédagogique patient [V/H]

**Déclenchement.** Demande explicite de fiche destinée au patient ou à ses proches, et non simple recherche médicale.

**Livrable.** Texte pédagogique clair, non technique, organisé pour une lecture et une impression faciles ; aperçu A4, idéalement une à deux pages lorsque le contenu s’y prête ; conseils, précautions et signes d’alerte adaptés au sujet. Sources en fin de document lorsqu’utiles. [V/H]

**Édition.** Modifier directement le texte ou donner des instructions de réécriture en langage naturel. Sauvegarde automatique locale des brouillons **sans validation médicale implicite**. [V]

**Validation et sortie.** Le PDF patient ne devient exportable **qu’après validation explicite de la version finale**. Ne jamais afficher un document comme imprimé, validé ou enregistré s’il ne l’est pas. [V]

**Frontière fonctionnelle.** FICH sert à produire des documents pédagogiques, **pas à gérer une bibliothèque personnelle de fiches médicales** ; cette dernière relève de l’historique/gestion des fiches de l’interface. [V]

## 4. Cahier des charges de l’interface React

### 4.1 Identité visuelle [V]

| Élément | Valeur validée |
|---|---|
| Style | Tableau de bord minimaliste, sombre, aéré, **pas un chat** |
| Thème | Sombre fixe, bleu nuit |
| Fond principal | `#141B24` |
| Surfaces | `#222D3A` |
| Accent | Turquoise discret `#72C6C7` |
| Texte | `#F1F5F9` |
| Police | Inter |
| Texte médical | 15 px par défaut, réglable de 14 à 18 px |
| Interligne | Environ 1,6 |
| Largeur fiche | Maximum 960 px, centrée, responsive |
| En-tête | Fixe lors du défilement |
| Logo | Logo **original fourni**, toujours à gauche du titre Gary, hauteur visuelle similaire |

Limiter les cartes, bordures décoratives et couleurs vives ; réserver la couleur aux états et vigilances réellement importants. [V]

### 4.2 Écran d’accueil et recherche [V]

- En-tête Gary et champ de recherche **centré** dans l’espace disponible.
- Supprimer les mentions « Recherche clinique », « Comment puis-je t’aider ? » et la liste de modules sous le champ.
- Sélecteur de module intégré à la recherche ; **AUTO par défaut**.
- `Entrée` soumet, `Maj+Entrée` insère une ligne.
- Après lancement, champ déplacé en haut par transition courte (environ 150–200 ms) ; **une fiche de résultat unique** apparaît, pas une succession de bulles.
- Nouvelle recherche : revenir à AUTO ; changement manuel de module : conserver le texte déjà saisi.
- Champs contextuels affichés sous la recherche uniquement pour les modules concernés, sans écran intermédiaire.

### 4.3 Génération et états [V/T]

- Présenter une transition courte puis un état « Génération en cours… » et un affichage progressif **lorsque le backend le permettra**.
- Pendant la recherche, messages humoristiques aléatoires parmi les douze phrases validées ; fréquence proposée historiquement de 5 à 7 secondes ; **les alertes et erreurs sont prioritaires**.
- Phrases validées : « Gary se creuse les méninges… », « Gary fouille dans les poubelles… », « Gary consulte les anciens… », « Gary interroge les méduses… », « Gary cherche la petite bête… », « Gary épluche les recommandations… », « Gary explore les profondeurs du savoir… », « Gary réveille ses neurones… », « Gary remonte la piste des preuves… », « Gary dépoussière les vieux grimoires… », « Gary suit la trace de l’escargot savant… », « Gary demande un deuxième avis à son coquillage… ».
- **Position de lecture stable** : aucun défilement automatique forcé pendant la génération.
- Nouvelle recherche/annulation : ne jamais mélanger les résultats de deux requêtes ; annulation sécurisée et état technique honnête.
- Échec complet : conserver question, module et paramètres ; afficher **Réessayer**.
- Si le backend ne permet pas encore le streaming, ne pas simuler une génération clinique réussie. [T]

### 4.4 Présentation des fiches [V]

- Titres et paragraphes courts, espacement confortable, tableaux adaptatifs sans perte d’information médicale.
- Actions sur la fiche discrètes, visibles au survol sur ordinateur, accessibles autrement sur tactile.
- Sommaire replié automatiquement disponible pour les fiches longues.
- Petite icône flottante de retour en haut après défilement.
- Références regroupées **en fin de fiche**, section repliée par défaut, avec provenance et liens réels ; ne pas attribuer de date non vérifiée.
- Rapport de doute replié par défaut ; alerte visible seulement si divergence cliniquement importante.
- Rendu correct des titres, listes, tableaux et liens : le rapport V5 signale qu’à ce stade les retours à la ligne sont conservés mais le Markdown n’est pas interprété. [T]

### 4.5 Ergonomie par module [V]

| Module | Comportement d’interface |
|---|---|
| AUTO | Afficher le module détecté ; changement manuel possible, sans confirmation préalable |
| DIAG | Hypothèses cliquables vers PATH ; remplacement de fiche avec retour possible |
| PATH | Sections pertinentes dynamiques ; accès contextuel à TTT et FICH |
| TTT | Fiche médicament ; adaptation rénale mise en avant |
| SUIVI | Âge, sexe, contexte ; quatre axes ; préférences personnelles étiquetées |
| PED | Âge, sexe, poids facultatif, contexte ; checklist adaptée |
| PREG | Terme en SA, contexte facultatif |
| ADM | Réponse libre et structurée selon la demande |
| FICH | Édition directe, instructions naturelles, aperçu A4, validation avant PDF |

Après une recherche, les informations de profil apparaissent en **étiquettes compactes** ; leur modification se fait par déploiement, puis actualisation seulement sur `Entrée` ou bouton **Actualiser**. Les commandes spécifiques ne s’affichent que lorsqu’elles sont utiles au module. [V]

### 4.6 Navigation et historique [V]

- Barre latérale **fermée par défaut**, superposée à la fiche sans déplacer le contenu.
- Accès à Recherche, Sources médicales, Mes fiches, Prompts et modes, Configuration et Historique (libellés ajustables sans modifier les fonctions).
- Historique **local persistant**, sans synchronisation automatique ; recherche dans l’historique, suppression individuelle, effacement global après confirmation.
- Réouverture : restaurer **question et réponse** instantanément, **sans appel API**.
- Afficher la date de génération et la commande **Actualiser la recherche** ; conserver la traçabilité des versions datées plutôt qu’écraser silencieusement une ancienne fiche.
- Au redémarrage : revenir à l’accueil, recherche active ; dernière fiche accessible dans l’historique.

### 4.7 Sources et préférences [V/T]

- Interface de **priorités documentaires**, pas une liste fictive de documents prétendument consultés.
- Pour ajouter une source : **deux champs, titre et URL** ; vérifier la cohérence et la validité formelle du lien avant sauvegarde, sans prétendre valider son contenu médical.
- Préférences documentaires distinctes par module lorsque nécessaire ; édition et ordre configurables.
- Les sources citées dans une réponse doivent correspondre à des sources effectivement consultées ou explicitement signalées comme non vérifiées.
- Les paramètres de cache CD/CR et leur durée de validité sont des **préférences choisies par le médecin**, pas des recommandations médicales ; leur éventuelle réutilisation ne doit jamais être présentée comme une actualisation documentaire.

### 4.8 Copie, impression, PDF et FICH [V]

- **Copier** : réponse principale uniquement ; action séparée **Copier avec les sources**.
- Impression des fiches médicales : fond blanc, texte noir, structure préservée.
- Export PDF des fiches médicales : références en fin de document.
- FICH : édition directe ou en langage naturel ; brouillon sauvegardé automatiquement en local ; export PDF **après validation explicite**, et jamais avant.

### 4.9 Raccourcis clavier [V]

| Raccourci | Fonction |
|---|---|
| `Entrée` | Lancer / actualiser la recherche |
| `Maj + Entrée` | Nouvelle ligne |
| `Ctrl + K` | Focus recherche |
| `Ctrl + N` | Nouvelle recherche |
| `Échap` | Fermer panneau/menu ou action contextuelle |
| `Alt + ←` | Revenir à la fiche précédente |

### 4.10 Réglages « Interface et API » [V/T]

- Réglage de taille de texte 14–18 px ; thème sombre fixe.
- Sélection de modèle dans la configuration, avec **`gpt-6.1-sol` comme choix historique demandé par défaut** ; disponibilité, tarifs et compatibilité doivent être vérifiés avant activation, et le nom d’un modèle affiché ne prouve pas un routage effectif. [V/T]
- Paramètres de profondeur, de contexte, de sources prioritaires et de cache accessibles sans surcharge de l’écran principal.
- Aucune dépense API ou génération réelle sans consentement commercial explicite, frais contrôlés et parcours techniquement qualifié. [T]

## 5. Architecture V5 et garde-fous techniques

### 5.1 Architecture retenue [T]

- Application locale Windows 11, ouverture dans Chrome via raccourci Gary ; interface React/Vite et backend Python local sur `127.0.0.1:8785`.
- Racine du projet : dossier `v5` de l’installation.
- Préférences et historique local SQLite ; clé API protégée via DPAPI ; requêtes OpenAI préparées localement.
- Ne **pas** recréer les moteurs V1–V4, les anciens environnements Python, Ollama, Chroma ou la chaîne RAG documentaire supprimée.
- Le projet après nettoyage est compact et autonome pour la **préparation locale**, mais **pas encore pour la génération LIVE depuis l’interface**.

### 5.2 Émission fournisseur et coût [T]

- État observé le 24 octobre : `TRANSPORT_ENABLED=False`, aucune route HTTP de génération ; `POST /api/prepare` prépare seulement la requête.
- Avant LIVE : nouvelle autorisation commerciale, dispositif budgétaire durable **distinct du registre du premier essai consommé**, réservation atomique, plafond, nombre d’appels, protection concurrence, recontrôle empreinte/fraîcheur, émission unique, suivi des coûts et des tentatives incertaines.
- Aucune répétition automatique après timeout ou erreur ; ne jamais considérer une interruption comme preuve de non-facturation.
- `store=false` et interdiction de journaliser les secrets ou informations directement identifiantes.
- L’adaptateur de réponse existe, mais le transport, l’enveloppe médicale et le rendu final doivent être raccordés et vérifiés de bout en bout.
- Les paramètres `max_output_tokens=2500`, `max_tool_calls=1`, `search_context_size=low`, raisonnement `low` sont **des réglages actuels**, non un cahier des charges médical intangible.

### 5.3 Préservation des données et interventions [V/T]

- Toute modification de prompts, UI ou backend doit partir de l’inventaire réel du code ; sauvegarde réversible ciblée et vérification après changement.
- Ne pas supprimer des données médicales, historiques, préférences ou registres de dépense sans demande explicite.
- Ne pas recréer le raccourci « Arrêter Gary » précédemment refusé sans nouvelle autorisation.
- Préserver les **cinq cas médicaux finaux réservés** pour la validation clinique ultérieure ; les tests techniques doivent rester distincts de cette validation.
- Ne pas multiplier les infrastructures de simulation, de test ou les rapports redondants ; privilégier des contrôles ciblés et les essais médicaux relus par le médecin.

## 6. Critères de recette fonctionnelle

| Domaine | Critère de conformité | Mode de vérification |
|---|---|---|
| AUTO | Choisit un seul module pertinent, respecte le préfixe explicite | Scénarios de routage hors API |
| DIAG | Hypothèses hiérarchisées, pas de traitement, liens PATH | Relecture médicale de réponse réelle |
| PATH | Maladie seule → fiche complète, diagnostic avant traitement | Relecture médicale de réponse réelle |
| TTT | Médicament, sécurité, adaptation rénale, CRAT selon question | Relecture médicale de réponse réelle |
| SUIVI | Quatre axes, fréquences, préférences personnelles identifiées | Relecture médicale de réponse réelle |
| PED | Checklist adaptée à l’âge, calendrier officiel | Relecture médicale de réponse réelle |
| PREG | Suivi adapté au terme en SA | Relecture médicale de réponse réelle |
| ADM | Conditions, juridiction et dates sans invention | Relecture réglementaire |
| FICH | Édition et brouillon local ; PDF seulement après validation | Parcours utilisateur |
| Interface | Accueil minimaliste, clavier, lecture stable, historique | Parcours navigateur |
| Sources | Provenance et liens réels, aucune source fictive | Contrôle de traçabilité |
| Confidentialité | Aucune fuite de clé ni donnée patient identifiante | Audit ciblé |
| API | Consentement et plafond avant chaque nouvelle campagne | Test hors réseau puis essai autorisé |

**La réussite des tests techniques ne vaut pas validation médicale.** La validation des réponses médicales est effectuée par le médecin sur des cas réels ou fictifs qu’il choisit, avec relecture de leur exactitude, de leur exhaustivité et de leur applicabilité.

## 7. Écarts et arbitrages restant à traiter

1. **Prompts médicaux trop courts :** le rapport V5 confirme le chargement des instructions, mais non leur conformité exhaustive aux contrats médicaux historiques. Comparer les fichiers de prompts à ce cahier des charges, sans réinventer de rubriques.
2. **TTT :** conflit entre ancien raccourci « TTT [pathologie] » et fiche médicament ; conserver la règle de routage déjà validée et résoudre explicitement l’ambiguïté.
3. **AUTO :** profondeur initiale provisoirement empruntée à DIAG ; l’aligner sur le module réellement résolu.
4. **Rendu :** le frontend actuel préserve les retours à la ligne mais n’interprète pas correctement tous les éléments Markdown ; assurer les titres, listes, tableaux et liens sûrs.
5. **LIVE :** raccordement et supervision budgétaire absents ; ne pas déverrouiller le transport isolément.
6. **Ancien RAG :** le cahier des charges V1–V4 mentionne recherche locale et Web ; la suppression volontaire des moteurs locaux rend cette partie **historique et non exigible telle quelle en V5**. Conserver les objectifs de qualité documentaire, pas l’ancienne implémentation.
7. **Granularité médicale :** les échanges détaillés de certains modules ne figurent pas intégralement dans l’export disponible ; les détails marqués [À préciser] ne doivent pas être présentés comme déjà validés.
8. **Fiches anciennes :** distinguer la consultation d’une version archivée d’une recherche actualisée ; afficher date et provenance.
9. **Cache :** distinguer les préférences de durée choisies par le médecin d’une garantie de fraîcheur médicale.
10. **Émission et coûts :** requalifier le modèle fournisseur, les tarifs, le budget et les limites avant toute nouvelle génération payante.

## 8. Plan de réalisation recommandé, conforme à l’esprit des décisions validées

**Phase A — Audit de conformité sans réécriture globale.** Comparer les prompts effectivement injectés, le routage, les contrats de réponse et les composants UI au présent document. Livrer un tableau « conforme / partiel / absent / contradictoire ».

**Phase B — Restauration ciblée des contrats médicaux.** Compléter les instructions de modules manquantes, sans changer la logique clinique validée ni recréer de moteur documentaire. Corriger l’ambiguïté TTT et la profondeur AUTO.

**Phase C — Finition de l’interface.** Réparer les écarts de rendu, navigation, historique, sources et FICH par petits changements réversibles, sans simuler la génération.

**Phase D — Activation contrôlée et validation clinique.** Après autorisation commerciale fraîche et superviseur de budget opérationnel, raccorder l’émission, puis procéder à des essais manuels relus par le médecin. Ne pas consommer les cinq cas finaux réservés avant le moment décidé.

## 9. Traçabilité des sources de cette consolidation

- **Export `conversations.json`**, conversation « Prompt recherche médicale structuré » : conception initiale PED, développements Gary, validations explicites d’ergonomie (messages de l’utilisateur autour des index chronologiques 1123–1165), prompt maître Codex et évolutions V5.
- **`Ok.txt`**, passage « AUTO — Fonctionnement déjà validé » et synthèse « Gary V1 — Architecture fonctionnelle » : orientation AUTO, navigation intermodules, liste des neuf modules, règles particulières TTT/SUIVI/PED/PREG/FICH.
- **`RAPPORT_RETABLISSEMENT_FONCTIONNEL_V5.md`**, 24 octobre 2026 : prompts réellement chargés, paramètres fournisseur, absence de route LIVE, état du transport et contrôles techniques.

**Fin du cahier des charges consolidé.**


## Décisions définitives — cache et futur workflow AUTO/Luna/Sol (27 octobre 2026)

Ces décisions prévalent sur les propositions historiques incompatibles.

- Le RAG historique est volontairement archivé et reste absent de V5. Aucune réintégration, réactivation ou préparation de raccordement dans les prochaines phases.
- Phase A prioritaire : intégration réelle de CD (documents/références Internet) et CR (réponses), dans le stockage local existant ; admission par contexte, instructions, provenance, dépendances, intégrité, TTL du médecin et révocations. Aucun historique utilisé comme substitut de CR, aucune fixture introduite en production. HIT/MISS/REJECT doivent être traçables.
- Phase B, après validation de A : consultation intégrale des prompts, contrats et paramètres existants en lecture seule ; examiner une éventuelle erreur « Instructions indisponibles », sans réviser les prompts médicaux.
- Phase C : routage GPT-6 Luna, désactivé par défaut. Sans préfixe spécialisé ou avec `AUTO :`, même classification ; préfixe DIAG/PATH/TTT/SUIVI/PED/PREG/ADM/FICH : sélection directe sans Luna. Un module principal, clarification en cas d’ambiguïté ; aucune génération médicale par Luna. Décision validée et persistée côté serveur, sans seconde classification à la confirmation.
- Phase D : workflow supervisé Luna/Sol et cache ; Sol (`gpt-6.1-sol` actuellement) assure exclusivement la génération médicale selon le contrat et les préférences du module. Un CR admissible peut éviter cette génération. Une classification ne constitue aucune autorisation d’appeler Sol.
- Phase E : essais fonctionnels et médicaux après autorisation explicite. Aucun appel réel ni ancienne autorisation réutilisée implicitement ; budgets et registres existants préservés.
- À chaque transition : signaler les scripts temporaires susceptibles d’archivage et prévoir le retour arrière. Aucune phase suivante engagée avant validation de la précédente.

Le fonctionnement AUTO décrit ici est une cible décidée ; les phases C/D ne sont pas activées par la livraison du cache.

## Décisions du 28 octobre 2026 — Ordre obligatoire E1, E1 bis, E2

E1 prépare et qualifie hors réseau les modèles, paramètres, coûts, garde-fous et le futur raccordement. Sa livraison puis sa validation par le propriétaire sont requises avant de commencer E1 bis.

### E1 bis — Gestion des sources documentaires et qualification des accès Internet

Phase obligatoire avant E2 : interface normale de configuration des sources par URL, module, priorité et activation, préservant les préférences déjà validées. Identifier les accès publics, authentifiés, sous abonnement ou techniquement restreints ; étudier particulièrement VIDAL et eBMFrance. Définir une acquisition autorisée compatible CD, les échecs et indisponibilités, sans contourner les protections ni stocker d’identifiants en clair. Un accès navigateur ne prouve pas un droit d’extraction automatisée.

Les sources configurées sont prioritaires, jamais exclusives. Gary identifie le module, recherche selon les priorités, exploite le contenu réellement accessible et vérifie la couverture de la demande. Si elle est insuffisante, il élargit la recherche à d’autres sources médicales pertinentes et fiables. Les références distinguent sources configurées et complémentaires, référence seule, page effectivement consultée et extrait disponible. CD conserve seulement les contenus admissibles et leurs preuves, versions et dates disponibles. Une URL ne prouve aucune consultation ; aucun contenu inaccessible, recommandation, dose ou durée ne doit être inventé. Une couverture toujours insuffisante conduit à une réponse partielle explicite. Aucun réglage de recherche exclusivement limitée aux sources configurées.

Les tests E1 bis sont locaux, sans API payante, sans panneau permanent de test, sans RAG historique et sans altération des contrats, caches ou contrôles commerciaux existants.

**Aucun branchement API ni test LIVE Luna/Sol avant validation séparée de E1 et E1 bis et nouvelle autorisation explicite du propriétaire.** E2 reste une proposition de protocole, non une autorisation de transfert ou de dépense.

### E1 bis — Authentification des sources professionnelles (28 octobre 2026)

Windows DPAPI lié au compte Windows est la méthode locale privilégiée. Le futur coffre des sources documentaires doit être séparé du coffre API existant, qui reste inchangé sauf nécessité démontrée. Aucun mot de passe, cookie ou jeton en clair dans SQLite, configurations, journaux, traces ou exports ; aucun secret transmis à Luna, Sol ou un tiers. Déchiffrement uniquement pour l’authentification autorisée, exposition mémoire limitée, aucune réaffichage après enregistrement.

L’interface normale permettra d’enregistrer, modifier, tester et supprimer les identifiants ; gérer expiration, erreurs et authentifications supplémentaires ; proposer une connexion manuelle si nécessaire. Une connexion réussie ne prouve ni accès au contenu ni droit de réutilisation : les deux doivent être vérifiés séparément. Connexion automatique uniquement si les mécanismes et conditions d’utilisation des sources le permettent.

Après migration de poste/compte Windows, prévoir une nouvelle saisie ; aucune portabilité DPAPI automatique ni export des secrets en clair. Ces exigences sont planifiées pour E1 bis ; elles ne déclenchent pas son implémentation avant la validation d’E1. Aucun appel payant ni LIVE Luna/Sol pendant E1 bis.

## Décision du 28 octobre 2026 — séparation E1 bis / E1 ter

La phase E1 est acceptée dans son seul périmètre préparatoire hors réseau. E1 bis est autorisée pour la configuration, la qualification des accès publics et l’acquisition locale contrôlée de contenus autorisés. Elle exclut l’enregistrement d’identifiants et l’authentification automatisée. Les décisions antérieures concernant DPAPI et les sessions professionnelles sont désormais réservées à une phase distincte **E1 ter**, non commencée pendant E1 bis.

Les préférences et contrats médicaux, CD/CR et contrôles commerciaux sont conservés. Les sources restent prioritaires mais non exclusives. Une réponse HTTP, un texte extrait et une couverture médicale suffisante sont des propriétés distinctes. Les accès refusés, pages vides et informations médicales insuffisantes ne doivent pas être confondus. L’élargissement de recherche exige une insuffisance documentaire identifiée ; aucune interrogation payante ou traitement IA n’est autorisé par E1 bis.

Arrêt à la livraison d’E1 bis pour validation. Aucun E1 ter, raccordement réel Luna/Sol, dépense ou test E2 sans nouvelle validation/autorisation adaptée.
