import React,{useEffect,useRef,useState} from 'react';
import PatientDocument from './PatientDocument.jsx';
import {localAPI,localDownload,localBlob,patientPdfFilename} from './local-api.js';
const pdfPrerequisites={
 PATIENT_PDF_NODE_MISSING:'Node.js est introuvable. Vérifiez PATH ou GARY_PDF_NODE.',
 PATIENT_PDF_DEPENDENCIES_MISSING:'Dépendances PDF locales absentes. Vérifiez React, React DOM et esbuild.',
 PATIENT_PDF_PLAYWRIGHT_MISSING:'Playwright est introuvable. Vérifiez les dépendances locales ou GARY_PDF_PLAYWRIGHT.',
 PATIENT_PDF_BROWSER_UNAVAILABLE:'Le navigateur PDF ne démarre pas. Vérifiez Chrome ou GARY_PDF_BROWSER.'
};
export default function PatientEditor({id,onRewrite,onSaved}){
 const [draft,setDraft]=useState(null),[content,setContent]=useState(''),[message,setMessage]=useState(''),[preview,setPreview]=useState(false),[validator,setValidator]=useState(''),[approved,setApproved]=useState(false),[instruction,setInstruction]=useState(''),[privacy,setPrivacy]=useState(false),[busy,setBusy]=useState(false);
 const current=useRef(null),dirty=useRef(false),saving=useRef(false),alive=useRef(true),contentRef=useRef(''),pending=useRef(null),validatorEdited=useRef(false);
 useEffect(()=>{alive.current=true;localAPI('/api/local/draft/'+id).then(v=>{if(alive.current){current.current=v;setDraft(v);setContent(v.versions.at(-1).text);contentRef.current=v.versions.at(-1).text;dirty.current=false}}).catch(()=>setMessage('Brouillon indisponible.'));return()=>{alive.current=false}},[id]);
 useEffect(()=>{
  let active=true;
  validatorEdited.current=false;setApproved(false);setValidator('');
  localAPI('/api/local/draft/last-validator').then(value=>{
   if(active&&!validatorEdited.current)setValidator(value.validator);
  }).catch(()=>{});
  return()=>{active=false};
 },[id]);
 async function save(){
  if(saving.current)return pending.current;
  if(!dirty.current||!current.current)return current.current;
  saving.current=true;
  pending.current=(async()=>{try{
   while(dirty.current){const snapshot=contentRef.current;const value=await localAPI('/api/local/draft/save',{id,revision:current.current.revision,text:snapshot});current.current=value;dirty.current=contentRef.current!==snapshot;if(alive.current){setDraft(value);onSaved?.(value);setMessage(dirty.current?'Enregistrement des dernières modifications…':'Brouillon enregistré localement.')}}
   return current.current;
  }catch{if(alive.current)setMessage('Conflit ou erreur de stockage : texte conservé dans l’éditeur. Copiez-le avant de recharger.');return null}finally{saving.current=false}})();
  return pending.current;
 }
 useEffect(()=>{if(!dirty.current)return;const timer=setTimeout(save,700);return()=>clearTimeout(timer)},[content]);
 useEffect(()=>{const warn=e=>{if(dirty.current||saving.current){e.preventDefault();e.returnValue=''}};addEventListener('beforeunload',warn);return()=>{removeEventListener('beforeunload',warn);if(dirty.current)void save()}},[id]);
 if(!draft)return <p role="status">Chargement du brouillon…</p>;
 const savedText=draft.versions.at(-1).text,unchanged=content===savedText;
 const valid=unchanged&&draft.validation?.revision===draft.revision;
 const shown={...draft,versions:[{text:content}],validation:valid?draft.validation:null};
 return <section className="patient-editor" data-exclude-from-evidence><h2>Brouillon de fiche patient{draft.test?' — TEST':''}</h2><p>Autosauvegarde locale sans validation implicite. Ne saisissez pas de données directement identifiantes. Version {draft.revision}.</p>
  <label>Texte de la fiche patient<textarea aria-label="Texte de la fiche patient" value={content} maxLength={100000} onChange={e=>{setContent(e.target.value);contentRef.current=e.target.value;dirty.current=true;setApproved(false);setMessage('Modifications non approuvées — enregistrement en attente.')}}/></label>
  <button onClick={save}>Enregistrer maintenant</button><button onClick={()=>setPreview(!preview)}>Prévisualisation A4</button>
  {preview&&<div className="patient-preview-scroller"><PatientDocument draft={shown} approved={valid}/></div>}
  <details><summary>Demander une réécriture</summary><label>Instruction de réécriture<textarea value={instruction} maxLength={1000} onChange={e=>setInstruction(e.target.value)}/></label><label><input type="checkbox" checked={privacy} onChange={e=>setPrivacy(e.target.checked)}/>Cette fiche et cette instruction ne contiennent aucune donnée patient identifiable</label><p>Réécriture externe soumise aux mêmes autorisations commerciales ; la version actuelle reste conservée.</p><button disabled={busy||!privacy||!instruction.trim()} onClick={async()=>{setBusy(true);const v=await save();if(v)onRewrite?.(v,instruction);setBusy(false)}}>Préparer la réécriture</button></details>
  <fieldset><legend>Approbation de cette version par le médecin</legend><label>Nom ou identifiant du médecin<input value={validator} onChange={e=>{validatorEdited.current=true;setValidator(e.target.value)}} autoComplete="off"/></label><label className="cache-activation"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>J’ai relu cette version et j’autorise sa remise au patient</label><div><button disabled={!approved||!validator.trim()||busy} onClick={async()=>{setBusy(true);const v=await save();if(v)try{const result=await localAPI('/api/local/draft/approve',{id,revision:v.revision,validator,confirmed:true});current.current=result;setDraft(result);setApproved(false);onSaved?.(result);setMessage('Cette version a été approuvée par le médecin indiqué. Toute modification l’invalide.')}catch{setMessage('Approbation refusée : vérifiez la version enregistrée.')}setBusy(false)}}>Approuver cette version</button></div></fieldset>
  <button disabled={!valid||busy} onClick={async()=>{setBusy(true);try{const result=await localAPI('/api/local/draft/pdf',{id,revision:draft.revision});await localDownload('/api/local/patient-export/'+id+'/'+result.export_id+'/Fiche_patient.pdf',patientPdfFilename(draft.versions.at(-1).document_title??draft.title));setMessage('PDF de la version approuvée exporté.')}catch(error){setMessage(pdfPrerequisites[error.message]||'Export refusé ou échoué ; vérifier l’approbation actuelle. Aucune génération déclenchée.')}setBusy(false)}}>Exporter le PDF patient approuvé</button>
  <p role="status">{message}</p>{valid&&<p>Version approuvée par {draft.validation.validator} — {new Date(draft.validation.created_at).toLocaleString('fr-FR')}</p>}
 </section>
}

function DraftReader({id,onEdit,onDeleted}){
 const [draft,setDraft]=useState(null),[revision,setRevision]=useState(null),[pdf,setPDF]=useState(null);
 const [message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const alive=useRef(true),locked=useRef(false),exported=useRef(null);
 useEffect(()=>{
  alive.current=true;
  localAPI('/api/local/draft/'+id).then(value=>{if(alive.current){setDraft(value);setRevision(value.revision)}})
   .catch(()=>{if(alive.current)setMessage('Fiche indisponible.')});
  return()=>{alive.current=false};
 },[id]);
 useEffect(()=>()=>{if(pdf)URL.revokeObjectURL(pdf)},[pdf]);
 if(!draft)return <p role="status">{message||'Chargement de la fiche…'}</p>;
 const versions=draft.versions;
 const approved=versions.filter(version=>[...(draft.approvals||[]),draft.validation].some(a=>a?.revision===version.revision&&a.text_sha256===version.text_sha256));
 const version=versions.find(v=>v.revision===revision);
 const title=version.document_title??draft.title;
 const isApproved=approved.some(v=>v.revision===revision);
 async function document(action){
  if(locked.current||!isApproved)return;
  locked.current=true;setBusy(true);setMessage('');
  const tab=action==='print'?window.open('about:blank','_blank'):null;
  try{
   if(action==='print'&&!tab)throw Error('PRINT_WINDOW_BLOCKED');
   if(exported.current?.revision!==revision){
    const value=await localAPI('/api/local/draft/library-pdf',{id,revision});
    exported.current={revision,path:'/api/local/patient-export/'+id+'/'+value.export_id+'/Fiche_patient.pdf'};
   }
   const blob=await localBlob(exported.current.path);
   if(!alive.current){tab?.close();return}
   const url=URL.createObjectURL(blob);
   if(action==='preview')setPDF(url);
   else if(action==='download'){
    const link=window.document.createElement('a');link.href=url;link.download=patientPdfFilename(title);link.click();
    setTimeout(()=>URL.revokeObjectURL(url),2000);
   }else{
    tab.location.replace(url);
    setMessage('Imprimez la fiche depuis le lecteur PDF ouvert dans le nouvel onglet.');
    const timer=setInterval(()=>{if(tab.closed){clearInterval(timer);URL.revokeObjectURL(url)}},1000);
   }
  }catch(error){tab?.close();if(alive.current)setMessage(pdfPrerequisites[error.message]||'PDF indisponible. Vérifiez la version approuvée ou l’autorisation d’ouvrir un onglet.')}
  finally{locked.current=false;if(alive.current)setBusy(false)}
 }
 async function remove(){
  if(locked.current||!window.confirm('Supprimer la fiche “'+title+'” et toutes ses versions de Mes fiches ?'))return;
  locked.current=true;setBusy(true);
  try{
   await localAPI('/api/local/draft/delete',{id,revision:draft.revision,visibility_revision:draft.visibility_revision??0,confirmed:true});
   onDeleted(id);
  }catch{setMessage('Suppression refusée. Rouvrez la fiche pour vérifier son état.')}
  finally{locked.current=false;if(alive.current)setBusy(false)}
 }
 return <section aria-label="Consultation de la fiche">
  <h2>{title}</h2>
  <p>{isApproved?'Version '+revision+' — approuvée':'Brouillon — non approuvé'}</p>
  {approved.some(v=>v.revision!==draft.revision)&&<label>Version consultée<select disabled={busy} value={revision} onChange={e=>{setRevision(Number(e.target.value));setPDF(null)}}>
   <option value={draft.revision}>Version actuelle — {draft.validation?'approuvée':'brouillon'}</option>
   {approved.filter(v=>v.revision!==draft.revision).map(v=><option key={v.revision} value={v.revision}>Version {v.revision} — approuvée</option>)}
  </select></label>}
  {isApproved&&<div><button disabled={busy} onClick={()=>document('preview')}>Visualiser</button><button disabled={busy} onClick={()=>document('print')}>Imprimer</button><button disabled={busy} onClick={()=>document('download')}>Télécharger PDF</button></div>}
  <button disabled={busy} onClick={onEdit}>Reprendre la rédaction</button>
  <button disabled={busy} onClick={remove}>Supprimer cette fiche</button>
  <p role="status">{message}</p>
  {pdf?<iframe title="Aperçu PDF de la version approuvée" src={pdf} style={{width:'100%',height:'75vh',border:0}}/>:
   <div className="patient-preview-scroller"><PatientDocument draft={{...draft,versions:[version]}} approved={isApproved}/></div>}
 </section>
}

export function DraftsView({onOpen,onRewrite}){
 const [items,setItems]=useState([]),[id,setId]=useState(null),[message,setMessage]=useState('');
 const [editing,setEditing]=useState(false);
 const [deleted,setDeleted]=useState(null),[restoring,setRestoring]=useState(false);
 const listRequest=useRef(0);
 function load(){const request=++listRequest.current;localAPI('/api/local/drafts').then(v=>{if(request===listRequest.current)setItems(v.items)}).catch(()=>{if(request===listRequest.current)setMessage('Brouillons indisponibles.')})}
 function loadDeleted(){localAPI('/api/local/drafts/deleted').then(v=>setDeleted(v.items)).catch(()=>setMessage('Fiches supprimées indisponibles.'))}
 async function restore(item){
  if(restoring)return;
  setRestoring(true);
  try{
   await localAPI('/api/local/draft/restore',{id:item.id,revision:item.revision,visibility_revision:item.visibility_revision,confirmed:true});
   load();loadDeleted();setMessage('Fiche restaurée.');
  }catch{setMessage('Restauration refusée. Vérifiez l’état de la fiche.');loadDeleted()}
  finally{setRestoring(false)}
 }
 useEffect(load,[]);
 return <section className="page"><h1>Mes fiches</h1><p>Brouillons patients locaux. Aucun export final sans approbation explicite de la version.</p><button onClick={async()=>{try{const v=await localAPI('/api/local/draft/create',{title:'Nouvelle fiche patient',text:''});setId(v.id);setEditing(true);load()}catch{setMessage('Création refusée.')}}}>Créer un brouillon vierge</button>{items.map(v=><p key={v.id}><button onClick={()=>{setId(v.id);setEditing(false)}}>{v.document_title??v.title}</button> <span>{v.validation?'Approuvée':'Brouillon'}{v.test?' — TEST':''}</span></p>)}{id&&(editing?<><button onClick={()=>setEditing(false)}>Revenir à la consultation</button><PatientEditor key={id} id={id} onRewrite={onRewrite} onSaved={load}/></>:
 <DraftReader key={id} id={id} onEdit={()=>setEditing(true)} onDeleted={identity=>{setId(current=>current===identity?null:current);load();if(deleted!==null)loadDeleted();setMessage('Fiche supprimée de Mes fiches.')}}/>)}
 <details onToggle={event=>{if(event.currentTarget.open)loadDeleted()}}><summary>Restaurer une fiche supprimée</summary>
 {deleted?.length===0&&<p>Aucune fiche supprimée.</p>}
 {deleted?.map(item=><p key={item.id}>{item.document_title??item.title} <button disabled={restoring} onClick={()=>restore(item)}>Restaurer</button></p>)}</details>
 <p role="status">{message}</p></section>
}
