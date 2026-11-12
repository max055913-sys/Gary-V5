import React,{useEffect,useState} from 'react';
import {localAPI} from './local-api.js';

export default function UpdateSettings(){
 const [status,setStatus]=useState(null),[error,setError]=useState(false);
 const path='/api/local/updates';
 useEffect(()=>{
  let live=true;
  async function refresh(){
   try{const value=await localAPI(path);if(live){setStatus(value);setError(false)}}
   catch{if(live)setError(true)}
  }
  refresh();const timer=setInterval(refresh,5000);
  return()=>{live=false;clearInterval(timer)};
 },[]);
 async function action(suffix,data){
  try{setStatus(await localAPI(path+suffix,data));setError(false)}
  catch{setError(true)}
 }
 return <section aria-label="Mises à jour"><h2>Mises à jour</h2>
  {status&&<><p>Version installée {status.version}</p>
   <label><input type="checkbox" checked={status.automatic} onChange={event=>action('/preferences',{automatic:event.target.checked})}/> Recherche automatique tous les 7 jours</label>
   <p>Dernière vérification réussie {status.last_success?new Date(status.last_success*1000).toLocaleString('fr-FR'):'aucune'}</p>
   <button disabled={!status.configured||status.busy} onClick={()=>action('/check',{})}>Rechercher une mise à jour</button>
   {!status.configured&&<p>Canal indisponible. Aucun dépôt ni clé de confiance de publication n’est configuré.</p>}
   {status.offer&&status.ignored!==status.offer.version&&<div role="status">
    <p>Nouvelle version disponible {status.offer.version}</p><p>{status.offer.notes}</p>
    <button disabled={status.busy||status.verified===status.offer.version} onClick={()=>{if(window.confirm('Télécharger la mise à jour vérifiée ?'))action('/download',{version:status.offer.version,confirmed:true})}}>Télécharger</button>
    <button onClick={()=>action('/preferences',{ignore:status.offer.version})}>Différer</button>
   </div>}
   {status.verified&&<div>
    <p role="status">Archive vérifiée.</p>
    <button disabled={status.busy} onClick={()=>{if(window.confirm('Installer cette mise à jour et arrêter Gary ?'))action('/install',{version:status.verified,confirmed:true})}}>Installer</button>
   </div>}
   {status.error&&<p role="status">L’opération de mise à jour a échoué. Réessayez ultérieurement.</p>}
  </>}
  {error&&<p role="status">Réglages de mise à jour indisponibles.</p>}
 </section>
}
