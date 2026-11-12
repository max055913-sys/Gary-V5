import React from 'react';

const modules=[
 ['AUTO','Sélection automatique du module','AUTO Hypercalcémie'],
 ['DIAG','Orientation diagnostique','DIAG Douleur thoracique aiguë'],
 ['PATH','Prise en charge d’une pathologie','PATH Hypertension artérielle'],
 ['TTT','Informations sur un médicament','TTT Amoxicilline'],
 ['SUIVI','Surveillance médicale','SUIVI Femme 66 ans diabète type II'],
 ['PED','Pédiatrie','PED Nourrisson de 4 mois'],
 ['PREG','Grossesse et allaitement','PREG Suivi grossesse 24 SA'],
 ['ADM','Administratif médical','ADM Condition rechute accident de travail'],
 ['FICH','Fiche d’information patient','FICH Dermatite atopique'],
];

export default function UserGuide(){
 return <section className="page" aria-labelledby="guide-title">
  <h1 id="guide-title">Mode d’emploi</h1>
  <section aria-labelledby="mise-en-route">
   <h2 id="mise-en-route" tabIndex={-1}>Mise en route</h2>
   <h3>Comment fonctionne Gary ?</h3>
   <p>Gary est une application locale Windows. La génération médicale utilise les modèles GPT d’OpenAI via Internet. Luna sélectionne automatiquement le module et intervient dans certaines comparaisons sémantiques lorsque ces fonctions sont disponibles. Sol analyse les documents et rédige les réponses médicales. OpenAI peut facturer ces appels. Les caches peuvent en éviter certains.</p>
   <h3>Créer un compte OpenAI</h3>
   <p>Créez un compte sur <a href="https://platform.openai.com/" target="_blank" rel="noopener noreferrer">OpenAI Platform</a>. L’API est facturée séparément de ChatGPT. Un abonnement ChatGPT Plus ne fournit pas automatiquement des crédits API.</p>
   <h3>Configurer la facturation</h3>
   <p>L’API est facturée à l’utilisation. Le coût dépend notamment du modèle, du volume de texte traité et des outils utilisés. Vérifiez les <a href="https://developers.openai.com/api/docs/pricing" target="_blank" rel="noopener noreferrer">tarifs applicables</a> et suivez votre consommation sur OpenAI Platform. Commencez avec un petit budget et consultez les limites et alertes disponibles pour votre compte. Une alerte ou un budget de suivi peut laisser les requêtes continuer. Même une limite appliquée peut prendre effet avec un délai.</p>
   <h3>Créer une clé API</h3>
   <ol><li>Connectez-vous à OpenAI Platform.</li><li>Ouvrez la <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer">gestion des clés API</a>.</li><li>Créez une clé appropriée pour votre projet.</li><li>Copiez la clé et conservez-la de manière confidentielle.</li></ol>
   <h3>Enregistrer la clé dans Gary</h3>
   <ol><li>Ouvrez Gary puis <strong>Configuration et sauvegardes</strong>.</li><li>Dans <strong>Connexion OpenAI</strong>, collez la clé et cliquez sur <strong>Enregistrer la clé</strong>.</li><li>Vérifiez la présence du masque <code>********</code> et du message « Clé API enregistrée ».</li><li>Cochez <strong>Activer l’accès API</strong> lorsque vous souhaitez autoriser les appels.</li></ol>
   <p>Windows DPAPI protège le secret dans un coffre local lié à votre compte Windows. L’état « enregistrée » confirme sa présence locale. La validité de la clé, la facturation et l’accès réseau ne sont vérifiés qu’auprès du fournisseur.</p>
   <h3>Effectuer sa première recherche</h3>
   <p>Dans Recherche, saisissez une question médicale, éventuellement précédée d’un préfixe de module, puis cliquez sur <strong>Générer</strong>. Lisez la réponse et consultez les références documentaires proposées. Les appels aux modèles exigent une configuration API fonctionnelle.</p>
   <h3>Confidentialité</h3>
   <p>Les informations soumises aux modèles GPT sont transmises à l’API OpenAI. Évitez les données patients identifiables et respectez vos obligations professionnelles de confidentialité et de conformité. Une clé API est un secret à garder privé.</p>
  </section>
  <details open>
   <summary>Démarrer une recherche</summary>
   <p>Dans Recherche, saisissez votre question, choisissez AUTO ou un module spécialisé, puis cliquez sur <strong>Générer</strong>. Le sélecteur de profondeur permet de choisir une réponse rapide, standard ou approfondie, ou de garder le réglage du module.</p>
   <p>Une nouvelle requête envoyée à OpenAI peut être facturée, y compris la classification en AUTO.</p>
  </details>
  <details>
   <summary>Choisir le bon module</summary>
   <p>Gary propose neuf modes, dont huit modules spécialisés. Commencez la question par le préfixe du module, suivi d’un espace, par exemple <code>PATH Hypertension artérielle</code>. Dans le sélecteur, gardez AUTO ou choisissez le même module que le préfixe.</p>
   <p>En mode AUTO, sans préfixe spécialisé ou avec le préfixe AUTO, Luna peut sélectionner le module. Cet appel supplémentaire peut être facturé. Les huit préfixes spécialisés sélectionnent directement leur module et évitent l’appel Luna de routage. La génération par Sol peut être facturée dans les deux cas. Les caches peuvent éviter certains appels selon les résultats déjà disponibles.</p>
   <table className="guide-modules"><thead><tr><th scope="col">Module</th><th scope="col">Fonction</th><th scope="col">Exemple</th></tr></thead>
    <tbody>{modules.map(([name,description,example])=><tr key={name}><th scope="row">{name}</th><td>{description}</td><td><code>{example}</code></td></tr>)}</tbody>
   </table>
  </details>
  <details>
   <summary>Préciser le contexte clinique</summary>
   <p>Ajoutez les éléments utiles dans la question ou dans les champs proposés par le module, par exemple l’âge en années, le contexte, le terme en semaines d’aménorrhée ou le DFG. Vérifiez le contexte affiché avant de générer, notamment après avoir reformulé une question.</p>
   <p>Évitez toute donnée directement identifiante, comme le nom, les coordonnées ou la date de naissance du patient.</p>
  </details>
  <details>
   <summary>Utiliser Mes fiches</summary>
   <p>Générez une fiche avec FICH, relisez-la, corrigez-la si nécessaire, puis approuvez explicitement la version à remettre au patient. Une modification du texte exige une nouvelle approbation pour exporter la nouvelle version.</p>
   <p>Dans Mes fiches, ouvrez la fiche en lecture seule. Vous pouvez visualiser, télécharger ou imprimer une version approuvée. Une ancienne version approuvée reste sélectionnable si elle est disponible. Pour modifier le brouillon, choisissez <strong>Reprendre la rédaction</strong>. La suppression de la fiche demande une confirmation et reste réversible depuis la liste.</p>
  </details>
  <details>
   <summary>Historique et caches</summary>
   <p>Retrouvez les consultations enregistrées dans Historique. Le cache CR peut réutiliser une réponse admissible. Le cache CD peut réutiliser des documents ou références admissibles. Leur activation et leurs durées se règlent par module.</p>
   <p>Une durée de cache valide ne garantit pas l’actualité médicale. Vérifiez la date et la provenance lorsque la décision dépend d’une mise à jour.</p>
  </details>
  <details>
   <summary>Sources médicales</summary>
   <p>Ajoutez les sources dans la bibliothèque, puis choisissez et classez celles à privilégier pour chaque module. Ces priorités orientent la recherche. D’autres sources publiques peuvent être consultées. L’accès effectif dépend de la disponibilité et des conditions du site.</p>
  </details>
  <details>
   <summary>Configuration, sauvegardes et dépenses</summary>
   <h3>Démarrage avec Windows</h3>
   <p>Cochez « Démarrer Gary automatiquement avec Windows » pour lancer le serveur en arrière-plan à l’ouverture de votre session. Le démarrage n’ouvre pas le navigateur et ne lance aucun appel API. Ouvrez l’interface avec le raccourci Gary du Bureau. Décochez la case pour désactiver les prochains démarrages automatiques.</p>
   <p>Utilisez « Arrêter Gary » ou « Redémarrer Gary » dans les réglages. Si le démarrage automatique échoue, ouvrez Gary avec le raccourci du Bureau pour obtenir un message d’erreur.</p>
   <p>Dans Configuration et sauvegardes, gérez la clé et l’activation de l’API OpenAI, les réglages de consultation et les caches. La clé reste chiffrée sur ce PC. Configurez le budget et les alertes du projet chez OpenAI et consultez-y les dépenses facturées.</p>
   <p>Pour sauvegarder ou restaurer les données, arrêtez Gary proprement et suivez la notice d’installation locale. Conservez ensemble la base, les documents et leurs preuves. Sur un autre poste, une nouvelle saisie de la clé peut être nécessaire.</p>
  </details>
  <details>
   <summary>En cas d’erreur</summary>
   <p>Une erreur technique de routage est distincte d’une demande de clarification. Si Gary propose une reprise, cliquez sur <strong>Générer</strong> et lisez la confirmation avant de l’accepter. La tentative précédente a pu être facturée. Gary ne relance pas automatiquement.</p>
   <p>Annuler interrompt l’attente dans le navigateur. Une requête déjà transmise peut continuer et être facturée. Un arrêt demandé pendant une opération est différé jusqu’à sa fin.</p>
  </details>
 </section>;
}
