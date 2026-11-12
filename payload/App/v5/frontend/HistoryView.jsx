import React,{useEffect,useState} from 'react';
import {localAPI} from './local-api.js';
export default function HistoryView({onOpen,onRefresh}){
 const [items,setItems]=useState([]),[query,setQuery]=useState(''),[module,setModule]=useState(''),[record,setRecord]=useState(null),[selected,setSelected]=useState(''),[message,setMessage]=useState('');
 async function load(){try{setItems((await localAPI('/api/local/history?q='+encodeURIComponent(query)+'&module='+module)).items)}catch{setMessage('Historique indisponible ou corrompu ; aucune génération déclenchée.')}}
 useEffect(()=>{const t=setTimeout(load,200);return()=>clearTimeout(t)},[query,module]);
 async function open(id){try{const r=await localAPI('/api/local/history/'+id);setRecord(r);setSelected(r.versions.at(-1).id)}catch{setMessage('Fiche indisponible ; aucun appel API.')}}
 const version=record?.versions.find(v=>v.id===selected);
 return <section className="page"><h1>Historique local</h1><p>Versions conservées sur ce PC. Leur consultation ne les actualise pas et n'appelle pas OpenAI. Aucun identifiant patient ne doit être enregistré.</p>
  <label>Rechercher dans l’historique<input value={query} onChange={e=>setQuery(e.target.value)}/></label>
  <label>Filtrer par module<select value={module} onChange={e=>setModule(e.target.value)}><option value="">Tous</option>{['DIAG','PATH','TTT','SUIVI','PED','PREG','ADM','FICH'].map(m=><option key={m}>{m}</option>)}</select></label>
  {items.length===0&&<p>Aucune consultation enregistrée dans cette sélection.</p>}
  {items.map(h=><article className="source" key={h.id}><h2>{h.question}</h2><p>{h.module} · {new Date(h.created_at).toLocaleString('fr-FR')} · {h.versions} version(s) · {h.state}{h.test?' · TEST':''}</p><button onClick={()=>open(h.id)}>Consulter les versions</button><button onClick={async()=>{if(!window.confirm('Supprimer cette consultation de l’historique ? Les preuves techniques restent conservées.'))return;try{await localAPI('/api/local/history/delete',{id:h.id,revision:h.revision,confirmed:true});if(record?.id===h.id)setRecord(null);load()}catch{setMessage('Suppression refusée : rechargez l’historique.')}}}>Supprimer cette consultation</button></article>)}
  {record&&version&&<section><h2>Versions de {version.question}</h2><label>Version à consulter<select value={selected} onChange={e=>setSelected(e.target.value)}>{record.versions.map((v,i)=><option key={v.id} value={v.id}>Version {i+1} — {new Date(v.created_at).toLocaleString('fr-FR')} — {v.state}</option>)}</select></label><button onClick={()=>onOpen(record,version)}>Ouvrir cette version sans génération</button><button onClick={()=>onRefresh(record,version)}>Actualiser la recherche</button></section>}
  <button onClick={async()=>{try{const all=(await localAPI('/api/local/history')).items;if(!all.length)return;if(!window.confirm('Supprimer les '+all.length+' consultations de tout l’historique local ? Les preuves restent conservées.'))return;await localAPI('/api/local/history/purge',{count:all.length,confirmed:true});setRecord(null);load()}catch{setMessage('Purge refusée : l’historique a pu changer.')}}}>Effacer tout l’historique</button><p role="status">{message}</p>
 </section>
}
