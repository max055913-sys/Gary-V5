import React,{useEffect,useState} from 'react';
import {localAPI} from './local-api.js';

const autostartPath='/api/local/windows-autostart';

function WindowsAutostart(){
 const [status,setStatus]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const [refresh,setRefresh]=useState(0);
 useEffect(()=>{
  let active=true;
  localAPI(autostartPath).then(result=>{
   if(active)setStatus(result);
  }).catch(()=>{
   if(active)setMessage('Impossible de lire l’état de la tâche Windows. Actualisez son état pour réessayer.');
  });
  return ()=>{active=false};
 },[refresh]);
 async function change(enabled){
  setBusy(true);setMessage('');
  try{
   setStatus(await localAPI(autostartPath,{enabled}));
  }catch(error){
   const operation=enabled?'Activation':'Désactivation';
   setMessage(error.message==='AUTOSTART_TASK_MODIFIED'
    ?'La tâche a été modifiée en dehors de Gary. Aucun changement appliqué.'
    :error.message==='AUTOSTART_MANAGED_SERVER_REQUIRED'
     ?'Ouvrez Gary avec son raccourci Windows pour modifier ce réglage.'
     :operation+' non confirmée par le Planificateur Windows.');
   try{setStatus(await localAPI(autostartPath))}catch{setStatus(null)}
  }finally{setBusy(false)}
 }
 const modified=status?.state==='MODIFIED';
 return <div>
  <label className="cache-activation"><input type="checkbox" checked={status?.enabled===true} disabled={!status||modified||busy} onChange={e=>change(e.target.checked)}/> Démarrer Gary automatiquement avec Windows</label>
  <p role="status">{busy?'Vérification auprès du Planificateur Windows…':message||(modified?'La tâche Windows a été modifiée en dehors de Gary. Ce réglage est verrouillé.':status?'Lorsque cette option est activée, Gary démarre en arrière-plan à l’ouverture de session. Utilisez le raccourci du Bureau pour ouvrir l’interface.':'Lecture de l’état du démarrage automatique…')}</p>
  {!status&&message&&!busy&&<button type="button" onClick={()=>{setMessage('');setRefresh(value=>value+1)}}>Actualiser l’état</button>}
 </div>;
}
export default function LocalWindows({configuration=false}){
 const [enabled,setEnabled]=useState(false);
 const [session,setSession]=useState(null),[configured,setConfigured]=useState(false),[key,setKey]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[active,setActive]=useState(true);
 useEffect(()=>{let alive=true;async function refresh(){try{const [s,k]=await Promise.all(['/api/windows/session','/api/openai/key/status'].map(u=>fetch(u).then(r=>{if(!r.ok)throw Error();return r.json()})));if(alive){setSession(s);setConfigured(k.configured);setEnabled(k.api_enabled===true);setActive(true)}}catch{if(alive)setActive(false)}}refresh();const id=setInterval(refresh,5000);return()=>{alive=false;clearInterval(id)}},[]);
 async function action(path,body){setBusy(true);setMessage('');try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Gary-Session':session.token},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error('Opération locale refusée.');if(path.includes('shutdown')){setMessage(d.result.state==='STOP_DEFERRED'?'Arrêt prévu après l’opération en cours. Si elle reste bloquée, un arrêt forcé peut laisser un appel déjà émis facturable.':'Arrêt de Gary demandé.')}else if(path==='/api/openai/enabled'){setEnabled(d.result.enabled);setMessage(d.result.enabled?'Accès API activé.':'Accès API désactivé.')}else{setConfigured(d.result.configured);setMessage(d.result.configured?'Clé enregistrée sur ce PC. Aucun appel API effectué.':'Clé supprimée. Les autres paramètres sont conservés.')}}catch{setMessage('Opération locale refusée ou serveur arrêté.')}finally{setKey('');setBusy(false)}}
 if(configuration)return <><WindowsAutostart/><div aria-label="Connexion OpenAI"><h3>Connexion OpenAI</h3><p>La clé reste sur ce PC, chiffrée par Windows DPAPI pour votre compte. Elle n'est jamais renvoyée par le serveur. Activer l’accès autorise les appels à la demande, avec facturation selon votre compte API.</p><label className="cache-activation"><input type="checkbox" checked={enabled} disabled={!active||!session||busy} onChange={e=>action('/api/openai/enabled',{enabled:e.target.checked})}/> Activer l’accès API</label><p role="status">{configured?<><span aria-hidden="true">********</span> Clé API enregistrée</>:'Clé API non configurée'}</p><label>Clé API OpenAI<input type="password" autoComplete="off" spellCheck="false" value={key} onChange={e=>setKey(e.target.value)}/></label><button disabled={!active||!session||busy||!key} onClick={()=>action('/api/openai/key',{action:'save',key})}>Enregistrer la clé</button><button disabled={!active||!session||busy||!configured} onClick={()=>{if(window.confirm('Supprimer la clé OpenAI enregistrée sur ce PC ?'))action('/api/openai/key',{action:'delete'})}}>Supprimer la clé</button><p role="status">{message}</p></div></>;
 async function restart(){
  if(!window.confirm('Redémarrer Gary maintenant ?'))return;
  setBusy(true);setMessage('Redémarrage de Gary en cours…');
  try{
   const r=await fetch('/api/windows/restart',{method:'POST',headers:{'Content-Type':'application/json','X-Gary-Session':session.token},body:JSON.stringify({action:'restart'})});
   const d=await r.json();
   if(d.error==='GENERATION_IN_PROGRESS'){setMessage('Une génération est en cours. Terminez-la ou annulez-la avant de redémarrer.');return}
   if(!r.ok||d.result?.state!=='RESTARTING')throw Error();
   const deadline=Date.now()+45000;
   while(Date.now()<deadline){
    await new Promise(resolve=>setTimeout(resolve,500));
    try{
     const reply=await fetch('/api/windows/session',{cache:'no-store',signal:AbortSignal.timeout(1500)});
     const next=reply.ok?await reply.json():null;
     if(next?.managed&&next.restart_supported&&next.instance&&next.instance!==d.result.instance){location.reload();return}
    }catch{}
   }
   setMessage('Gary n’a pas répondu après le redémarrage. Relancez-le depuis le Bureau.');
  }catch{setMessage('Redémarrage refusé ou indisponible. Vérifiez que Gary est actif.')}
  finally{setBusy(false)}
 }
 return <div aria-label="État local Gary"><p role="status">{active?'Gary local actif':'Gary local arrêté ou indisponible'}</p><button disabled={!session?.managed||!active||busy} onClick={()=>{if(window.confirm('Arrêter Gary pour tous les onglets ouverts ?'))action('/api/windows/shutdown',{action:'stop'})}}>Arrêter Gary</button><br/><button disabled={!session?.restart_supported||!active||busy} onClick={restart}>Redémarrer Gary</button><p role="status">{message}</p></div>;
}
