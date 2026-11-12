import React,{useEffect,useRef,useState} from 'react';
import {adapt,validate,safeURL,additionalSources} from './result-contract.mjs';
import Markdown from './Markdown.jsx';
import PatientEditor from './PatientEditor.jsx';
import {localAPI} from './local-api.js';
const LABELS={complete:'Réponse complète',partial:'Réponse partielle',clarification:'Clarification requise',refusal:'Refus',technical_error:'Erreur technique',insufficient_sources:'Sources insuffisantes'};
function dateLabel(value){if(value===undefined||value===null||value==='')return null;const d=new Date(typeof value==='number'?value*1000:value);return Number.isNaN(d.getTime())?null:d.toLocaleString('fr-FR')}
export default function ResultCard({raw,onPath,onNavigate,onRewrite}){
 const article=useRef(null);
 const [copyMessage,setCopyMessage]=useState(''),[headings,setHeadings]=useState([]),[cacheRejected,setCacheRejected]=useState(false),[cacheMessage,setCacheMessage]=useState('');
 useEffect(()=>{setCacheRejected(false);setCacheMessage('')},[raw]);
 useEffect(()=>{setHeadings([...article.current?.querySelectorAll(':scope > .source-text [data-rendered-response] h2,:scope > .source-text [data-rendered-response] h3')||[]].map(e=>e.textContent))},[raw]);
 async function rejectCached(){setCopyMessage('');try{await localAPI('/api/cr/reject',{id:raw.cache?.entry_id||raw.cache_entry_id,reason:null});setCacheRejected(true);setCacheMessage('Réutilisation rejetée. La réponse affichée est conservée ; aucun nouvel appel.')}catch{setCacheMessage('Signalement non enregistré : erreur de stockage.')}}
 let r;try{r=validate(adapt(raw))}catch{return <section role="alert"><h2>Erreur technique</h2><p>Contrat du résultat refusé.</p></section>}
 const supplemental=r.presentation_text!==undefined?r.sources:additionalSources(r.summary,r.sources);
 const blocking=['refusal','technical_error','clarification','insufficient_sources'].includes(r.status);
 const cached=raw.cache?.kind==='CR',exact=raw.cache?.match==='EXACT'||raw.cache?.decision==='HIT'&&raw.cache?.reason==='ADMISSIBLE',match=raw.cache?.match==='SEMANTIC'?'correspondance sémantique':exact?'correspondance exacte':'type de correspondance non renseigné';
 const generated=dateLabel(raw.cache?.generated_at||raw.generated_at||raw.provider_created_at||raw.created_at),consulted=cached?dateLabel(raw.cache.read_at):null;
 const origin=r.test?'TEST HORS RÉSEAU — '+(cached?'réponse issue du cache CR — '+match:'réponse simulée, non utilisable médicalement'):r.preparation?'Requête préparée — aucun appel API':r.simulation?'Simulation — non utilisable médicalement':cached?'Réponse issue du cache CR — '+match:'Réponse générée par Sol';
 async function copy(withSources){try{const text=article.current.querySelector(':scope > .source-text')?.innerText||'';const sources=withSources&&r.sources.length?'\n\nSources\n'+r.sources.map(s=>[s.title,s.publication_date,s.url].filter(Boolean).join(' — ')).join('\n'):'';await navigator.clipboard.writeText(text+sources);setCopyMessage(withSources?'Texte et références copiés.':'Texte copié.')}catch{setCopyMessage('Copie refusée par le navigateur.')}}
 return <article ref={article} className="sheet" aria-label="Résultat documentaire">
  <h1>{r.title}</h1>
  {(r.provisional||r.status==='partial'||blocking)&&<p className="response-state" role={blocking?'alert':'status'}>{r.provisional?'Réponse en cours — provisoire, références non finalisées.':blocking?LABELS[r.status]:'Réponse partielle — contenu incomplet.'}</p>}
  <div className="source-text">{(r.presentation_fragments||r.fragments)?(r.presentation_fragments||r.fragments).map((f,i)=><Markdown key={i} text={f.text} annotations={f.annotations} references={r.sources}/>):<Markdown text={r.summary}/>}</div>
  <pre hidden style={{display:'none'}} data-raw-response>{r.summary}</pre>
  {r.sections.map((s,i)=><section key={i}><h3>{s.title}</h3><div className="source-text"><Markdown text={s.text}/></div><blockquote className="source-text">{s.quote}</blockquote><p>{s.citation_ids.map(id=><a key={id} href={'#source-'+id} onClick={e=>{e.preventDefault();document.getElementById('source-'+id)?.scrollIntoView()}}>[{id}] </a>)}</p></section>)}
  {r.presentation_text!==undefined?<section className="bibliography" aria-label="Sources"><h2>Sources</h2>{r.sources.length===0&&(r.bibliography_unlinked||[]).length===0&&<p>Aucune référence fournie.</p>}<ol>{r.sources.map(s=><li key={s.id} id={'source-'+s.id}>{s.notices?.length?s.notices.map((n,i)=><Markdown key={i} text={n}/>):safeURL(s.url)?<a href={s.url} target="_blank" rel="noopener noreferrer">{s.title||'Source'}{s.publication_date?' ('+s.publication_date+')':''}</a>:<span>{s.title||'Référence sans lien fiable'}</span>}</li>)}</ol>{(r.bibliography_unlinked||[]).map((line,i)=><Markdown key={i} text={line}/>)}</section>:supplemental.length>0&&<details className="source-details" aria-label="Références documentaires"><summary>Références documentaires</summary>{supplemental.map(s=><div id={'source-'+s.id} key={s.id} className="source"><h3>{s.title}</h3>{safeURL(s.url)&&!s.fictional?<a href={s.url} target="_blank" rel="noopener noreferrer">{s.title||'Consulter la source'}</a>:<span>Référence sans lien fiable</span>}{s.publication_date&&<p>{s.publication_date}</p>}</div>)}</details>}
  {r.module==='FICH'&&!r.preparation&&raw.draft_id&&<PatientEditor key={raw.draft_id} id={raw.draft_id} onRewrite={onRewrite}/>}
  <footer className="response-footer" aria-label="Provenance et actions de la réponse">
   <p className="response-origin">{origin}</p><p>Module : {r.module}{generated?' · Génération initiale : '+generated:''}{consulted?' · Consultation : '+consulted:''}</p>
   <h2>{r.provisional?'Réponse en cours — provisoire':LABELS[r.status]}</h2>
   {cached&&<p>Aucune nouvelle génération. La durée choisie ne garantit pas l’actualité médicale.</p>}
   {raw.web_actions?.length>0&&<p>Actions Web reçues ; citations conservées. La lecture intégrale des pages n’est pas démontrée.</p>}
   {raw.cache_warning&&<p role="alert">{raw.cache_warning}</p>}{raw.local_save_warning&&<p role="alert">{raw.local_save_warning}</p>}
   {r.missing_profile.length>0&&<p>Profil à compléter : {r.missing_profile.join(', ')}</p>}
   <section><h3>Vigilance et limites</h3>{r.warnings.map((w,i)=><p key={i}>{w}</p>)}</section>
   {headings.length>3&&<details className="toc"><summary>Sommaire de la fiche</summary>{headings.map((h,i)=><button key={i} onClick={()=>article.current.querySelectorAll(':scope > .source-text [data-rendered-response] h2,:scope > .source-text [data-rendered-response] h3')[i]?.scrollIntoView({block:'start'})}>{h}</button>)}</details>}
   <div className="response-actions" data-exclude-from-evidence>
    <button disabled={!!r.provisional} onClick={()=>copy(false)}>Copier le texte</button><button disabled={!!r.provisional} onClick={()=>copy(true)}>Copier avec les sources</button><button disabled={!!r.provisional} onClick={()=>window.print()}>Imprimer sur fond blanc</button>
    {(raw.cache?.entry_id||raw.cache_entry_id)&&<button disabled={cacheRejected||!!r.provisional} onClick={rejectCached}>Signaler une anomalie</button>}
    {cached&&<a href="#/historique">Actualiser depuis l’historique</a>}
   </div><p className="response-action-feedback" role="status" data-exclude-from-evidence>{copyMessage||cacheMessage}</p>
   {({DIAG:['PATH'],PATH:['TTT','FICH'],PED:['PATH'],PREG:['TTT']}[r.module]||[]).length>0&&<nav className="intermodule-nav" aria-label="Ouvrir un autre module">{({DIAG:['PATH'],PATH:['TTT','FICH'],PED:['PATH'],PREG:['TTT']}[r.module]||[]).map(m=><button key={m} disabled={!!r.provisional} onClick={()=>onNavigate?onNavigate(m):onPath?.()}>Ouvrir {m} sans génération</button>)}</nav>}
  </footer>
 </article>
}
