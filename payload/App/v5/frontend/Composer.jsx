import React,{useEffect,useRef,useState} from 'react';
import {localAPI} from './local-api.js';
const MODULES=['AUTO','DIAG','PATH','TTT','SUIVI','PED','PREG','ADM','FICH'];
export function requestProfile(profile,confirmed){
 if(!confirmed)return {};
 const p={};
 for(const k of ['sex','weight','term','context'])if(profile[k]?.trim())p[k]=profile[k].trim();
 if(profile.age?.trim())p.age=profile.age.trim()+' ans';
 return p;
}
export default function Composer({model,setModel,question,setQuestion,profile,setProfile,onResult,inputRef,generationBusy=false,lunaRetry=null,restore=null,historyId=null}){
 const [depths,setDepths]=useState({}),[depth,setDepth]=useState('inherit'),[context,setContext]=useState('intermediaire'),[busy,setBusy]=useState(false),[error,setError]=useState('');const [includePersonal,setIncludePersonal]=useState(false),[renal,setRenal]=useState('');
 const sequence=useRef(0),abort=useRef(null),inflight=useRef(false),freshFields=useRef(new Set());
 useEffect(()=>{let active=true;fetch('/api/documentary/settings').then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{if(active)setDepths(Object.fromEntries(Object.entries(d.value.modules).map(([m,g])=>[m,g.depth])))}).catch(()=>{if(active)setError('Préférences de profondeur indisponibles.')});return()=>{active=false;sequence.current++;abort.current?.abort()}},[]);
 useEffect(()=>{if(!restore){setDepth('inherit');setRenal('')}},[question]);
 useEffect(()=>{localAPI('/api/local/options').then(v=>{if(!restore)setContext(v.context_policy)}).catch(()=>{})},[]);
 useEffect(()=>{freshFields.current.clear();setRenal('');setIncludePersonal(false)},[model]);
 useEffect(()=>{if(restore){freshFields.current.clear();setRenal('');setIncludePersonal(false);setDepth(restore.depth||'inherit');setContext(restore.context_policy||'intermediaire')}},[restore?.token]);
 useEffect(()=>{sequence.current++;abort.current?.abort();inflight.current=false;setBusy(false);if(!restore)onResult(null)},[question,model,profile,depth,context,renal,includePersonal]);
 function cancel(){sequence.current++;abort.current?.abort();inflight.current=false;setBusy(false);setError('Attente interrompue dans le navigateur. Une requête déjà envoyée peut continuer et être facturée. La saisie est conservée.')}
 function field(k,v){freshFields.current.add(k);setProfile(p=>({...p,[k]:v}))}
 async function run(e){e.preventDefault();if(inflight.current||generationBusy)return;
 const retry=lunaRetry?.previous;
 if(retry){
  const warning=lunaRetry.emission==='NOT_SENT'?'':' La tentative précédente a pu être facturée.';
  if(!window.confirm('Lancer une nouvelle classification Luna ?'+warning))return;
 }
 setError('');if(!question.trim())return setError('Saisissez une question.');inflight.current=true;setBusy(true);const id=++sequence.current;const clicked=performance.now();const controller=new AbortController();abort.current=controller;
 const visible=model==='AUTO'?[]:model==='PED'?['age','sex','weight','context']:model==='SUIVI'?['age','sex','context']:model==='PREG'?['term','context']:['context'];
 const entered=Object.fromEntries(Object.entries(profile).filter(([k])=>visible.includes(k)&&freshFields.current.has(k)));
 if(entered.age?.trim()&&!/^\d+(?:[.,]\d+)?$/.test(entered.age.trim())){
  inflight.current=false;setBusy(false);setError('Saisissez un âge en années, sans unité.');return;
 }
 const p=requestProfile(entered,true);
 try{const sessionReply=await fetch('/api/windows/session');if(!sessionReply.ok)throw Error();const sessionToken=(await sessionReply.json()).token;const r=await fetch('/api/generation/prepare',{method:'POST',headers:{'Content-Type':'application/json','X-Gary-Session':sessionToken},signal:controller.signal,body:JSON.stringify({query:question,module:model,profile:p,...(depth==='inherit'?{}:{depth}),context_policy:context,model:'auto-luna-sol',...(retry?{luna_retry:retry}:{}),...(historyId?{history_id:historyId}:{}),include_personal_suivi:includePersonal,...(model==='TTT'&&renal!==''?{renal_context:{kind:'REPORTED_EGFR',value:renal}}:{})})});const d=await r.json();if(!r.ok)throw Error(d.error);if(id===sequence.current)onResult({...d.result,client_started_ms:clicked,ui_parameters:{depth,context,module:model,question,profile:p},depth_executed:false})}catch(e){if(id===sequence.current)setError(e.name==='AbortError'?'Attente interrompue dans le navigateur. Une requête déjà envoyée peut continuer et être facturée.':e.message==='POTENTIALLY_IDENTIFYING_DATA_REFUSED'?'Données potentiellement identifiantes détectées : retirez les identifiants avant de poursuivre. Aucun enregistrement ni appel.':e.message==='RENAL_CONTEXT_INVALID'?'DFG invalide : saisissez une valeur numérique positive ou nulle.':e.message==='MODULE_CONTRADICTOIRE'?'Conflit : le préfixe et le module sélectionné diffèrent. Corrigez l’un des deux.':'Préparation locale refusée ou serveur indisponible.')}finally{if(id===sequence.current){inflight.current=false;setBusy(false)}}}
 return <><form className="composer" onSubmit={run}><fieldset className="generation-fields" disabled={generationBusy}><label className="sr-only" htmlFor="clinical-question">Votre question</label><textarea id="clinical-question" ref={inputRef} value={question} onChange={e=>setQuestion(e.target.value)} maxLength={1000} placeholder="Votre question" onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form.requestSubmit()}}}/><div className="composer-tools"><label>Module<select aria-label="Module" value={model} onChange={e=>setModel(e.target.value)}>{MODULES.map(m=><option key={m}>{m}</option>)}</select></label><label>Profondeur de réponse<select aria-label="Profondeur de réponse" value={depth} onChange={e=>setDepth(e.target.value)}><option value="inherit">{model==='AUTO'?'Par défaut du module résolu':'Par défaut : '+(depths[model]||'chargement…')}</option>{[['rapide','Rapide'],['standard','Standard'],['approfondie','Approfondie']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><button disabled={busy||generationBusy} type="submit">{generationBusy?'Traitement en cours…':busy?'Préparation…':'Générer'}</button></div>
 {model!=='AUTO'&&<div className={'profile grid'+(['SUIVI','PED'].includes(model)?' profile-patient':'')}>{['SUIVI','PED'].includes(model)&&<><label>Âge (facultatif)<input inputMode="decimal" value={profile.age||''} onChange={e=>field('age',e.target.value)}/></label><label>Sexe (facultatif)<select aria-label="Sexe (facultatif)" value={profile.sex||''} onChange={e=>field('sex',e.target.value)}><option value="">Choisir</option><option>Féminin</option><option>Masculin</option></select></label></>}{['PREG'].includes(model)&&<label>Terme de grossesse facultatif (SA)<input type="number" min="0" max="45" step="0.1" value={profile.term||''} onChange={e=>field('term',e.target.value)}/></label>}<label>Contexte (facultatif)<textarea aria-label="Contexte (facultatif)" value={profile.context||''} onChange={e=>field('context',e.target.value)} maxLength={500}/></label>{['PED'].includes(model)&&<label>Poids facultatif (kg)<input value={profile.weight||''} onChange={e=>field('weight',e.target.value)}/></label>} </div>}
 {model==='SUIVI'&&<label><input type="checkbox" checked={includePersonal} onChange={e=>setIncludePersonal(e.target.checked)}/>Inclure les préférences personnelles SUIVI enregistrées (distinctes des recommandations officielles)</label>}
 {model==='TTT'&&<label>DFG (mL/min/1,73 m²)<input type="number" min="0" step="any" inputMode="decimal" value={renal} onChange={e=>setRenal(e.target.value)}/></label>}
 </fieldset></form>{busy&&<p role="status">Préparation locale en cours… <button onClick={cancel}>Annuler</button></p>}{error&&<p role="alert">{error}</p>}</>
}
