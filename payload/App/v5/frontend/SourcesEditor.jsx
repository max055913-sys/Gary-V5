import React,{useState,useEffect,useRef} from 'react';
import {localAPI} from './local-api.js';
// Preserve path and query bytes while comparing the HTTPS authority.
function referenceURL(value){
 if(!value)return null;
 const match=/^https:\/\/([^/?#]+)([^?#]*)(\?[^#]*)?$/i.exec(value);
 if(!match||match[1].includes('@'))return value;
 try{
  const host=new URL('https://'+match[1]);
  if(host.port)return value;
  return 'https://'+host.hostname+(match[2]||'/')+(match[3]||'');
 }catch{return value}
}
export function registeredPriorities(sources,library){
 return sources.map((source,index)=>{
  const explicit=source.provenance==='CATALOG_SOURCE';
  const matches=library.filter(entry=>explicit?'catalog_'+entry.id===source.id:
   source.url?referenceURL(entry.url)===referenceURL(source.url):entry.title===source.title);
  const match=matches.length===1?matches[0]:null;
  return {...source,index,libraryId:match?.id,registered:match,
   ambiguous:matches.length>1?matches:[]};
 });
}
export default function SourcesEditor({module,onChanged=()=>{},prioritiesOnly=false,libraryRevision=0}){
 const drag=useRef(null);
 const [dropTarget,setDropTarget]=useState(null);
 const dirty=useRef(false),saving=useRef(false);
 const [busy,setBusy]=useState(false),[conflict,setConflict]=useState(false),[latest,setLatest]=useState(null);
 const [envelope,setEnvelope]=useState(null),[library,setLibrary]=useState([]),[selection,setSelection]=useState(''),[message,setMessage]=useState('');const m=module==='AUTO'?'DIAG':module;
 useEffect(()=>{let active=true;Promise.all([fetch('/api/documentary/settings').then(r=>{if(!r.ok)throw Error();return r.json()}),localAPI('/api/local/web-sources')]).then(([e,l])=>{if(active){setEnvelope(e);setLibrary(l.value.sources)}}).catch(()=>setMessage('Préférences indisponibles.'));return()=>{active=false}},[]);
 useEffect(()=>{setSelection('');setMessage('');clearDrag()},[m]);
 useEffect(()=>{if(!libraryRevision)return;let active=true;Promise.all([localAPI('/api/local/web-sources'),fetch('/api/documentary/settings').then(r=>r.json())]).then(([l,e])=>{if(active){setLibrary(l.value.sources);if(!dirty.current&&!saving.current)setEnvelope(current=>!current||e.value.revision>=current.value.revision?e:current);else setMessage('La bibliothèque a changé ; vos modifications non enregistrées sont conservées.')}}).catch(()=>setMessage('Actualisation de la bibliothèque impossible.'));return()=>{active=false}},[libraryRevision]);
 if(!envelope)return <p role="status">{message||'Chargement des préférences…'}</p>;
 const value=envelope.value,group=value.modules[m],priorities=registeredPriorities(group.sources,library);
 function change(patch){dirty.current=true;setEnvelope(e=>({...e,value:{...e.value,modules:{...e.value.modules,[m]:{...e.value.modules[m],...patch}}}}));onChanged();setMessage('Modifications non enregistrées.')}
 function move(from,to){
  if(!group.sources[from]||!group.sources[to]||from===to||busy)return;
  const sources=[...group.sources];
  sources.splice(to,0,sources.splice(from,1)[0]);
  change({sources});
 }
 function clearDrag(){drag.current=null;setDropTarget(null)}
 function startDrag(event,source){
  drag.current={module:m,id:source.id};
  event.dataTransfer.setData('text/plain',source.id);
  event.dataTransfer.effectAllowed='move';
 }
 function drop(event,index){
  if(drag.current?.module!==m)return;
  event.preventDefault();
  const from=group.sources.findIndex(source=>source.id===drag.current.id);
  clearDrag();move(from,index);
 }
 function remove(source){change({sources:group.sources.filter((_,index)=>index!==source.index)})}
 function add(){const source=library.find(s=>s.id===selection);if(!source)return;const id='catalog_'+source.id;if(group.sources.some(s=>s.id===id||s.url&&s.url===source.url||!s.url&&s.title===source.title)){setMessage('Cette source figure déjà dans les priorités du module.');return}change({sources:[...group.sources,{id,title:source.title,url:source.url,provenance:'CATALOG_SOURCE'}]});setSelection('')}
 async function save(){
  if(saving.current||conflict)return;
  saving.current=true;setBusy(true);
  try{
   const r=await fetch('/api/documentary/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value,revision:value.revision})});
   const d=await r.json();
   if(!r.ok)throw Error(d.error);
   setEnvelope(d.result);dirty.current=false;setLatest(null);
   setMessage('Préférences enregistrées localement.');onChanged();
  }catch(e){
   if(e.message==='REVISION_CONFLICT')setConflict(true);
   setMessage(e.message==='REVISION_CONFLICT'?'Les préférences ont changé. Vos modifications sont conservées.':'Enregistrement refusé : vérifiez que les sources existent toujours dans la bibliothèque.');
  }finally{saving.current=false;setBusy(false)}
 }
 async function review(){
  try{
   const r=await fetch('/api/documentary/settings');
   if(!r.ok)throw Error();
   setLatest(await r.json());
  }catch{setMessage('Préférences actuelles indisponibles. Votre brouillon est conservé.')}
 }
 function reload(){
  if(!window.confirm('Abandonner les modifications de préférences non enregistrées ?'))return;
  setEnvelope(latest);dirty.current=false;setConflict(false);setLatest(null);
  setMessage('Préférences actuelles rechargées.');
 }
 return <fieldset disabled={busy}><legend>{prioritiesOnly?"Sources prioritaires — "+m:"Sources du module "+m}</legend>
 <h3>Sources prioritaires</h3>{envelope.legacy_assignment_review_required?.includes(m)&&<p>Anciennes affectations retrouvées. Vérifiez l’ordre proposé avant de l’enregistrer ; les priorités médicales existantes sont conservées en tête.</p>}<p>Le rang correspond à l’ordre des préférences transmises pour ce module. Sol peut aussi consulter d’autres sources publiques.</p>{priorities.length===0&&<p>Aucune source prioritaire configurée pour ce module.</p>}{priorities.map((s,i)=><div className={'source priority-source'+(dropTarget===s.id?' priority-drop':'')} key={s.id}
 onDragOver={event=>{if(!busy&&drag.current?.module===m){event.preventDefault();event.dataTransfer.dropEffect='move';setDropTarget(s.id)}}}
 onDrop={event=>drop(event,i)}><p><span className="priority-grip" draggable={!busy} title="Glisser pour déplacer la source" aria-hidden="true" onDragStart={event=>startDrag(event,s)} onDragEnd={clearDrag}>⠿</span> {i+1}. {s.title}</p><p>{s.provenance==='CATALOG_SOURCE'?'Fiche de la bibliothèque':'Référence historique · '+s.provenance}{s.registered?.access_kind==='PUBLIC'?' · Source '+(s.registered.enabled?'activée':'désactivée'):''}</p>{s.ambiguous.length>0&&<p>Référence historique ambiguë : {s.ambiguous.map(entry=>entry.title+' ('+entry.id+')').join(', ')}.</p>}<p className="source-url">{s.url||'Référence utilisée par son titre.'}</p><button type="button" disabled={i===0} aria-label={'Monter '+s.title} onClick={()=>move(i,i-1)}>Monter</button><button type="button" disabled={i===priorities.length-1} aria-label={'Descendre '+s.title} onClick={()=>move(i,i+1)}>Descendre</button><button type="button" onClick={()=>remove(s)}>{prioritiesOnly?"Retirer":"Retirer du module"}</button></div>)}
 <label>Ajouter une source existante<select aria-label="Ajouter une source existante" value={selection} onChange={e=>setSelection(e.target.value)}><option value="">Choisir dans la bibliothèque</option>{library.filter(s=>!priorities.some(p=>p.libraryId===s.id)).map(s=><option key={s.id} value={s.id}>{s.title}</option>)}</select></label><button type="button" disabled={!selection} onClick={add}>{prioritiesOnly?"Ajouter":"Ajouter au module"}</button>{library.length===0&&<p>Ajoutez d’abord une source dans la bibliothèque « Sources médicales ».</p>}
 {!prioritiesOnly&&<section aria-label="Préférences documentaires"><h3>Préférences documentaires</h3><label>Profondeur de réponse<select aria-label="Profondeur de réponse" value={group.depth} onChange={e=>change({depth:e.target.value})}>{['rapide','standard','approfondie'].map(d=><option key={d}>{d}</option>)}</select></label><label>Sites Internet à privilégier (facultatif)<textarea value={group.preferred_domains.join('\n')} onChange={e=>change({preferred_domains:e.target.value.split('\n').map(s=>s.trim().toLowerCase()).filter(Boolean)})}/></label></section>}
 <button type="button" disabled={conflict} onClick={save}>Enregistrer les préférences documentaires</button>
 {conflict&&<button type="button" onClick={review}>Consulter les priorités actuelles</button>}
 {latest&&<section aria-label="Préférences actuelles"><h3>Préférences actuelles — {m}</h3>
 <p>Profondeur : {latest.value.modules[m].depth}</p>
 <p>Sites privilégiés : {latest.value.modules[m].preferred_domains.join(', ')||'Aucun'}</p>
 <ol>{latest.value.modules[m].sources.map(source=><li key={source.id}>{source.title}</li>)}</ol>
 <button type="button" onClick={reload}>Recharger les préférences et abandonner le brouillon</button></section>}<p role="status">{message}</p></fieldset>
}
