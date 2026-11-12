import UserGuide from './UserGuide.jsx';
import React,{useEffect,useRef,useState} from 'react';
import Composer from './Composer.jsx';
import ResultCard from './ResultCard.jsx';
import GenerationPanel from './GenerationPanel.jsx';

import {Preferences,Sources} from './Preferences.jsx';
import HistoryView from './HistoryView.jsx';
import ModesView from './ModesView.jsx';
import {DraftsView} from './PatientEditor.jsx';
import {localAPI,localDownload} from './local-api.js';
import logo from './logo.png';import LocalWindows from './LocalWindows.jsx';
export const MODULES=['AUTO','DIAG','PATH','TTT','SUIVI','PED','PREG','ADM','FICH'];
const NAV=[['recherche','Recherche'],['historique','Historique'],['sources','Sources médicales'],['fiches','Mes fiches'],['guide','Mode d’emploi'],['prompts','Prompts et modes'],['configuration','Configuration et sauvegardes']];
function OpenAISetupNotice(){
 const [needed,setNeeded]=useState(false);
 useEffect(()=>{
  let active=true;
  async function refresh(){
   try{
    const reply=await fetch('/api/health',{cache:'no-store'});
    if(!reply.ok)return;
    const health=await reply.json();
    if(active)setNeeded(health.transport===false);
   }catch{}
  }
  refresh();
  const timer=setInterval(refresh,5000);
  return()=>{active=false;clearInterval(timer)};
 },[]);
 return needed&&<aside className="setup-notice">
  <strong>API OpenAI non configurée — Génération indisponible</strong>
  <p>Pour utiliser Gary, configurez votre clé API OpenAI. Consultez la rubrique Mise en route du mode d'emploi.</p>
  <a href="#/guide">Voir le mode d'emploi</a>
 </aside>;
}
export default function GaryApp(){
 const [route,setRoute]=useState(()=>location.hash.slice(2)||'recherche'),[drawer,setDrawer]=useState(false),[module,setModule]=useState('AUTO'),[question,setQuestion]=useState(''),[profile,setProfile]=useState({}),[result,setResult]=useState(null),[liveDisplay,setLiveDisplay]=useState(null),[generationBusy,setGenerationBusy]=useState(false),[archive,setArchive]=useState(null),[restore,setRestore]=useState(null),[historyId,setHistoryId]=useState(null),[stack,setStack]=useState([]),[fontSize,setFontSize]=useState(15),[atTop,setAtTop]=useState(true);const menu=useRef(null),panel=useRef(null),input=useRef(null);
 useEffect(()=>{localAPI('/api/local/options').then(v=>setFontSize(v.font_size)).catch(()=>{});const scroll=()=>setAtTop(scrollY<500);addEventListener('scroll',scroll,{passive:true});return()=>removeEventListener('scroll',scroll)},[]);
 function close(){setDrawer(false);menu.current?.focus()}
 useEffect(()=>{const change=()=>{setRoute(location.hash.slice(2)||'recherche');setDrawer(false)};addEventListener('hashchange',change);return()=>removeEventListener('hashchange',change)},[]);
 useEffect(()=>{if(drawer)panel.current?.querySelector('button')?.focus()},[drawer]);
 useEffect(()=>{if(route==='recherche')input.current?.focus();else if(route==='guide')document.getElementById('mise-en-route')?.focus();else document.getElementById('main')?.focus()},[route]);
 useEffect(()=>{const keys=e=>{if(e.key==='Escape'&&drawer){e.preventDefault();close()}if(e.ctrlKey&&e.key.toLowerCase()==='n'){e.preventDefault();fresh()}if(e.altKey&&e.key==='ArrowLeft'){e.preventDefault();back()}if(e.ctrlKey&&e.key.toLowerCase()==='k'){e.preventDefault();location.hash='/recherche';input.current?.focus()}};addEventListener('keydown',keys);return()=>removeEventListener('keydown',keys)},[drawer,generationBusy,stack]);
 function fresh(){if(generationBusy)return;setRestore(null);setArchive(null);setHistoryId(null);setStack([]);setQuestion('');setModule('AUTO');setProfile({});setResult(null);setLiveDisplay(null);location.hash='/recherche';input.current?.focus()}
 function snapshot(){return {module,question,profile,result,liveDisplay,archive,restore,historyId,scroll:scrollY}}
 function restoreSnapshot(v){setRestore({...v.restore,token:Date.now(),profileConfirmed:!!Object.keys(v.profile).length});setModule(v.module);setQuestion(v.question);setProfile(v.profile);setResult(v.result);setLiveDisplay(v.liveDisplay);setArchive(v.archive);setHistoryId(v.historyId);location.hash='/recherche';requestAnimationFrame(()=>requestAnimationFrame(()=>scrollTo(0,v.scroll||0)))}
 function back(){if(generationBusy||!stack.length)return;const previous=stack.at(-1);setStack(stack.slice(0,-1));restoreSnapshot(previous)}
 function navigate(target){if(generationBusy)return;setStack(v=>[...v,snapshot()]);setRestore({token:Date.now(),depth:'inherit',context_policy:restore?.context_policy||'intermediaire',profileConfirmed:false});setModule(target);setResult(null);setLiveDisplay(null);setArchive(null);setHistoryId(null);location.hash='/recherche';input.current?.focus()}
 function openHistory(record,version,refresh=false){if(generationBusy)return;if(liveDisplay)setStack(v=>[...v,snapshot()]);const profile=structuredClone(version.profile||{});const age=profile.age?.match(/^(.*)\s+ans$/);if(age)profile.age=age[1];setRestore({token:Date.now(),depth:version.depth||'inherit',context_policy:version.context_policy||'intermediaire',profileConfirmed:true,refresh,additional_context:version.additional_context||{}});setModule(version.module);setQuestion(version.question);setProfile(profile);setResult(null);setLiveDisplay(refresh?null:{...version.display,generated_at:version.display.cache?.generated_at||version.created_at,history_id:record.id,version_id:version.id});setArchive(refresh?null:{date:version.display.cache?.generated_at||version.created_at,version:record.versions.findIndex(v=>v.id===version.id)+1,id:record.id,versionId:version.id,test:version.test});setHistoryId(record.id);location.hash='/recherche';if(refresh)input.current?.focus()}
 async function rewrite(draft,instruction){if(generationBusy)return;setStack(v=>[...v,snapshot()]);setModule('FICH');setQuestion('Réécrire la fiche patient selon la demande fournie');setProfile({});setRestore({token:Date.now(),depth:'inherit',context_policy:'intermediaire'});location.hash='/recherche';try{const prepared=await localAPI('/api/generation/prepare',{module:'FICH',query:'Réécrire la fiche patient selon la demande fournie',privacy_confirmed:true,rewrite:{draft_id:draft.id,revision:draft.revision,instruction}});setResult(prepared);setLiveDisplay(null);setArchive(null);setHistoryId(null);setGenerationBusy(!!prepared.generation?.ready)}catch{setResult({schema:'gary_v5_prepared_v1',status:'clarification',module:'FICH',question:'Réécriture de fiche',message:'Préparation de réécriture refusée. Le brouillon reste conservé.'})}}
 function changeQuestion(value){setRestore(null);setArchive(null);setHistoryId(null);setQuestion(value)}
 function changeModule(value){setRestore(null);setProfile({});setHistoryId(null);setModule(value)}
 function prepared(value){setResult(value);setLiveDisplay(null);setArchive(null);setGenerationBusy(!!value?.generation?.ready)}
 return <div className="phase-one" style={{'--body-size':fontSize+'px'}}><a className="skip" href="#main" onClick={e=>{e.preventDefault();document.getElementById('main').focus()}}>Aller au contenu</a><header className="header"><button ref={menu} disabled={generationBusy} aria-label="Ouvrir le menu" aria-expanded={drawer} onClick={()=>setDrawer(!drawer)}>☰</button><a className="logo" href="#/recherche" onClick={fresh}><img src={logo} alt=""/><span>Gary</span></a><button className="new" disabled={generationBusy} aria-label="Nouvelle recherche" onClick={fresh}>＋<span>Nouvelle recherche</span></button></header>
 {drawer&&<><div className="scrim" onClick={close}/><aside ref={panel} role="dialog" aria-modal="true" aria-label="Navigation Gary" className="drawer" onKeyDown={e=>{if(e.key!=='Tab')return;const nodes=[...panel.current.querySelectorAll('button,a')],first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}}><button aria-label="Fermer le menu" onClick={close}>✕</button><nav>{NAV.map(([id,label])=><a key={id} className={id==='sources'||id==='prompts'?'nav-group-start':undefined} href={'#/'+id} aria-current={route===id?'page':undefined} onClick={()=>setDrawer(false)}>{label}</a>)}</nav></aside></>}
 <main id="main" tabIndex={-1} inert={drawer?true:undefined} className={route==='recherche'?'home'+(result||liveDisplay||restore?' submitted':''):''}>
 {route==='recherche'?<><OpenAISetupNotice/><Composer model={module} setModel={changeModule} question={question} setQuestion={changeQuestion} profile={profile} setProfile={value=>{setRestore(null);setArchive(null);setHistoryId(null);setProfile(value)}} generationBusy={generationBusy} lunaRetry={result?.luna_retry} restore={restore} historyId={historyId} onResult={prepared} inputRef={input}/>{stack.length>0&&<button disabled={generationBusy} onClick={back}>Revenir à la fiche précédente</button>}{(liveDisplay||(result&&!result.generation))&&<ResultCard raw={liveDisplay||result} onNavigate={navigate} onRewrite={rewrite}/>} {archive&&<aside className="archive-note">Version archivée {archive.version} — générée le {new Date(archive.date).toLocaleString('fr-FR')}. Aucune actualisation lors de la consultation.{restore?.additional_context&&<details><summary>Contexte complémentaire effectivement transmis</summary><pre>{JSON.stringify(restore.additional_context,null,2)}</pre><p>Une actualisation reprend les préférences courantes ; vérifiez les champs avant toute émission.</p></details>}<button onClick={()=>localDownload('/api/local/history-artifact/'+archive.id+'/'+archive.versionId+'/reponse_gary_brute.txt','reponse_gary_brute.txt').catch(()=>alert('Preuve indisponible ; aucun appel fournisseur.'))}>Télécharger le texte original archivé</button><button onClick={()=>localDownload('/api/local/history-artifact/'+archive.id+'/'+archive.versionId+'/'+(archive.test?'Gary_TEST_reponse_originale.pdf':'Gary_reponse_originale.pdf'),'reponse_archivee.pdf').catch(()=>alert('PDF indisponible ; originaux conservés.'))}>Télécharger le PDF archivé</button><button onClick={()=>{setArchive(null);setLiveDisplay(null);setRestore({...restore,token:Date.now(),refresh:true});input.current?.focus()}}>Actualiser la recherche</button></aside>} {result?.generation&&<GenerationPanel key={result.generation.id} preparation={result} onDisplay={setLiveDisplay} onBusy={setGenerationBusy} autoStart={!liveDisplay}/>}</>:route==='guide'?<UserGuide/>:route==='prompts'?<ModesView/>:route==='configuration'?<Preferences module={module} setModule={changeModule} onWorkspaceChanged={v=>setFontSize(v.font_size)}/>:route==='sources'?<Sources module={module} setModule={setModule}/>:route==='historique'?<HistoryView onOpen={(r,v)=>openHistory(r,v)} onRefresh={(r,v)=>openHistory(r,v,true)}/>:route==='fiches'?<DraftsView onRewrite={rewrite}/>:NAV.some(([id])=>id===route)?<section className="page"><h1>{NAV.find(([id])=>id===route)[1]}</h1><p>Vue préparée ; fonction non raccordée. Aucune donnée fictive présentée comme une bibliothèque réelle.</p></section>:<section><h1>Page introuvable</h1><a href="#/recherche">Recherche</a></section>}
 </main>{!atTop&&<button className="back-top" aria-label="Retour en haut" onClick={()=>scrollTo({top:0,behavior:'smooth'})}>↑</button>}</div>
}
