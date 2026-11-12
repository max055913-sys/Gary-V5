import React,{useEffect,useState,useRef} from 'react';
import {localAPI} from './local-api.js';
const CAPS={search:'Recherche',html:'Lecture de pages HTML',pdf:'Lecture de PDF',download:'Téléchargement de documents'};
const RIGHTS={consult:'Consultation par Gary',store_cd:'Conservation dans CD',inject_sol:'Transmission des contenus à Sol'};
export default function WebSources({onChanged=()=>{}}){
 const [env,setEnv]=useState(null),[draft,setDraft]=useState(null),[config,setConfig]=useState(null);
 const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[base,setBase]=useState(null);
 const [conflict,setConflict]=useState(false),[latest,setLatest]=useState(null);
 const pending=useRef(null);
 const saving=useRef(false);
 async function load(){
  try{setEnv(await localAPI('/api/local/web-sources'));return true}
  catch{setMessage('Bibliothèque indisponible. Vous pouvez la recharger.');return false}
 }
 useEffect(()=>{load()},[]);
 useEffect(()=>{if(draft)document.getElementById('source-configuration')?.focus()},[draft?.id]);
 function begin(source,connector,catalogue){
  setDraft(structuredClone(source));setConfig(structuredClone(connector));setMessage('');
  setBase({catalog_revision:catalogue.value.revision,preferences_sha256:catalogue.current_preferences_sha256});
  setConflict(false);setLatest(null);pending.current=null;
 }
 async function openDraft(identity){
  if(busy)return;
  setBusy(true);
  try{
   const catalogue=await localAPI('/api/local/web-sources');
   setEnv(catalogue);
   if(identity){
    const source=catalogue.value.sources.find(entry=>entry.id===identity);
    if(source?.access_kind!=='PUBLIC'){
     setMessage('Cette fiche publique a changé ou a été retirée.');return;
    }
    begin(source,catalogue.connectors[identity].value,catalogue);return;
   }
   const id='source_'+crypto.randomUUID();
   begin({id,title:'',url:null,domain:'',modules:{},enabled:true,access_kind:'PUBLIC',automation_allowed:false,local_reuse_allowed:false,external_ai_allowed:false,rights_evidence:''},
    {schema:'gary_source_connector_v1',source_id:id,revision:0,source_scope_sha256:'0'.repeat(64),enabled:true,access_type:'PUBLIC',declared_capabilities:{search:false,html:true,pdf:false,download:false},declared_rights:{consult:false,store_cd:false,inject_sol:false},rights_reference:''},catalogue);
  }catch{setMessage('Valeurs actuelles indisponibles. Réessayez pour ouvrir le brouillon.')}
  finally{setBusy(false)}
 }
 function change(patch){setDraft(s=>({...s,...patch}))}
 function error(e){
  if(e.message==='WEB_DUPLICATE_URL')return 'Cette URL correspond déjà à une source enregistrée.';
  if(['REVISION_CONFLICT','WEB_PREFERENCES_CHANGED','WEB_SOURCE_ASSIGNMENTS_CHANGED'].includes(e.message))return 'La bibliothèque, les priorités ou le connecteur ont changé. Votre brouillon est conservé. Consultez les valeurs actuelles avant de choisir.';
  if(e.message==='WEB_HISTORICAL_SOURCE_READ_ONLY')return 'Cette référence historique est protégée.';
  if(e.message==='WEB_SOURCE_IN_USE')return 'Retirez d’abord cette source des priorités des modules concernés.';
  return 'Enregistrement non confirmé. Réessayez avec les mêmes valeurs pour vérifier ou terminer la sauvegarde.';
 }
 async function review(){
  try{setLatest(await localAPI('/api/local/web-sources'))}
  catch{setMessage('Valeurs actuelles indisponibles. Votre brouillon est conservé.')}
 }
 function abandon(){
  if(!window.confirm('Abandonner les modifications non enregistrées ?'))return;
  const current=latest?.value.sources.find(source=>source.id===draft.id);
  if(latest){
   setEnv(latest);
   if(current?.access_kind==='PUBLIC'){begin(current,latest.connectors[current.id].value,latest);return}
  }
  setDraft(null);setConfig(null);setConflict(false);setLatest(null);pending.current=null;
  setMessage('Brouillon abandonné.');load();
 }
 async function save(){
  if(saving.current||busy||conflict)return;
  if(!draft.title.trim()||!draft.url&&!env.value.sources.some(source=>source.id===draft.id)){
   setMessage('Renseignez le nom et l’URL de la source.');return;
  }
  const values={...base,source:draft,connector:config};
  const serialized=JSON.stringify(values);
  if(pending.current?.serialized!==serialized)pending.current={serialized,operation_id:crypto.randomUUID()};
  saving.current=true;setBusy(true);
  try{
   const receipt=await localAPI('/api/local/web-sources/save',{...values,operation_id:pending.current.operation_id});
   if(!receipt.saved)throw Error('SAVE_NOT_CONFIRMED');
   setDraft(null);setConfig(null);pending.current=null;
   setEnv(null);
   const loaded=await load();
   setMessage(loaded?'Source enregistrée. Elle est disponible dans les priorités des modules.':'Source enregistrée. Rechargez la bibliothèque pour afficher les valeurs actuelles.');
   onChanged();
  }catch(e){
   if(['REVISION_CONFLICT','WEB_PREFERENCES_CHANGED','WEB_SOURCE_ASSIGNMENTS_CHANGED'].includes(e.message))setConflict(true);
   setMessage(error(e));
  }finally{saving.current=false;setBusy(false)}
 }
 async function remove(source){if(busy||!window.confirm('Retirer cette source de la bibliothèque et des priorités des modules ? Les preuves et caches conservés ne seront pas effacés.'))return;setBusy(true);try{const r=await localAPI('/api/local/web-sources',{value:{...env.value,preferences_sha256:env.current_preferences_sha256,sources:env.value.sources.filter(s=>s.id!==source.id)},revision:env.value.revision});setEnv(r);setMessage('Source retirée de la bibliothèque et des priorités des modules.');onChanged()}catch(e){setMessage(error(e))}finally{setBusy(false)}}
 if(!env)return <><p role="status">{message||'Chargement de la bibliothèque…'}</p>{message&&<button type="button" onClick={load}>Recharger la bibliothèque</button>}</>;
 const saved=draft&&env.value.sources.find(s=>s.id===draft.id);
 const current=latest?.value.sources.find(source=>source.id===draft?.id);
 const duplicates=new Set((env.duplicate_urls||[]).flat());
 return <section className="web-sources" aria-label="Bibliothèque des sources">
 {!draft&&<button type="button" onClick={()=>openDraft()} disabled={busy}>Ajouter une source</button>}
 {env.value.sources.length===0&&!draft&&<p>Aucune source enregistrée.</p>}
 {env.value.sources.map(s=><article className="source source-card" key={s.id}>
 <div className="source-card-heading"><strong>{s.title}</strong><span>{s.access_kind==='PUBLIC'?(s.enabled?'Activée':'Désactivée'):'Historique · Lecture seule'}</span></div>
 <p className="source-url">{s.url||'Référence sans URL'}</p>
 {duplicates.has(s.id)&&<p>URL partagée par plusieurs fiches historiques.</p>}
 {s.access_kind==='PUBLIC'&&draft?.id!==s.id&&<button type="button" disabled={busy||!!draft} onClick={()=>openDraft(s.id)}>Configurer</button>}
 {s.access_kind==='PUBLIC'&&!draft&&<details className="source-configuration"><summary>Gestion de la fiche</summary><button type="button" disabled={busy} onClick={()=>remove(s)}>Retirer la source</button></details>}

 </article>)}
 {draft&&<details className="source source-configuration" open>
 <summary id="source-configuration">{saved?'Configurer · '+saved.title:'Nouvelle source'}</summary>
 <fieldset disabled={busy} aria-label="Configuration de la source"><label>Nom de la source<input value={draft.title} maxLength={200} onChange={e=>change({title:e.target.value})}/></label><label>URL principale<input type="url" value={draft.url||''} onChange={e=>{let domain='';try{domain=new URL(e.target.value).hostname.toLowerCase()}catch{}change({url:e.target.value||null,domain})}}/></label><p>Domaine déduit : <output>{draft.domain||'À déterminer'}</output></p>
 <label><input type="checkbox" role="switch" checked={config.enabled} onChange={e=>setConfig(c=>({...c,enabled:e.target.checked}))}/>Connecteur activé</label>
 <p>Le Web public de Sol applique ses propres règles d’accès.</p>
 <button type="button" disabled={busy||conflict} onClick={save}>Enregistrer</button>
 <button type="button" disabled={busy} onClick={abandon}>Abandonner le brouillon</button>
 {conflict&&<button type="button" disabled={busy} onClick={review}>Consulter les valeurs actuelles</button>}
 {latest&&<section aria-label="Valeurs actuelles"><h3>Valeurs actuelles</h3>
 {current?<><p>{current.title} · {current.url||'Sans URL'} · {current.enabled?'Activée':'Désactivée'}</p>
 <details><summary>Réglages publics enregistrés</summary>
 <p>Connecteur {latest.connectors[current.id].value.enabled?'activé':'désactivé'}</p>
 <p>Capacités déclarées : {Object.entries(CAPS).filter(([key])=>latest.connectors[current.id].value.declared_capabilities[key]).map(([,label])=>label).join(', ')||'Aucune'}</p>
 <p>Droits déclarés : {Object.entries(RIGHTS).filter(([key])=>latest.connectors[current.id].value.declared_rights[key]).map(([,label])=>label).join(', ')||'Aucun'}</p>
 <p>Référence : {latest.connectors[current.id].value.rights_reference||'Aucune'}</p></details></>:<p>Cette fiche ne figure pas dans la bibliothèque actuelle.</p>}
 <button type="button" onClick={abandon}>Recharger ces valeurs et abandonner le brouillon</button></section>}</fieldset></details>}
 <p role="status">{message}</p></section>
}

