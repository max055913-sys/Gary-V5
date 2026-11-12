import React,{useEffect,useState} from 'react';
import {localAPI} from './local-api.js';
const MODULES=['AUTO','DIAG','PATH','TTT','SUIVI','PED','PREG','ADM','FICH'];
export default function ModesView(){
 const [module,setModule]=useState('AUTO'),[data,setData]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;setData(null);setError('');localAPI('/api/local/modes?module='+module).then(v=>{if(active)setData(v)}).catch(()=>{if(active)setError('Instructions indisponibles. Rechargez la page pour réessayer.')});return()=>{active=false}},[module]);
 return <section className="page modes-view"><h1>Prompts et modes</h1><p>Instructions et réglages de Gary, en lecture seule.</p>
 <label>Module à consulter<select value={module} onChange={e=>setModule(e.target.value)}>{MODULES.map(m=><option key={m}>{m}</option>)}</select></label>
 {error&&<p role="alert">{error}</p>}{!data&&!error&&<p role="status">Chargement des instructions…</p>}
 {data&&<div className="mode-content">
 <h2>{module==='AUTO'?'AUTO — orientation vers un seul module':module+' — contrat médical'}</h2>
 {module==='AUTO'&&<p>AUTO sélectionne un seul des huit modules médicaux. Le nouveau workflow Luna reste désactivé en production.</p>}
 {data.instructions.map((item,i)=><section className="instruction-block" key={i}><h3>{item.title}</h3><pre className="instruction-text">{item.text}</pre></section>)}
 <details><summary>Préférences conditionnelles</summary>{Object.entries(data.conditional_preferences||{}).map(([m,v])=><p key={m}><strong>{m}</strong> — {v}</p>)}<p>Leur application dépend de la demande et du contexte fourni.</p></details>
 {data.assembled&&<details><summary>Instructions complètes assemblées</summary><pre className="instruction-text">{data.assembled.text}</pre></details>}
 {data.preparatory_semantic&&<section className="instruction-block"><h3>AUTO Luna et comparaison CD/CR — désactivés</h3><pre className="instruction-text">{data.preparatory_semantic.instructions.text}</pre></section>}
 <h3>Réglages de préparation</h3><div className="table-scroll"><table><thead><tr><th>Réglage</th><th>Valeur</th></tr></thead><tbody>{Object.entries(data.fixed_parameters||{}).map(([k,v])=><tr key={k}><th scope="row">{k}</th><td><code>{JSON.stringify(v)}</code></td></tr>)}</tbody></table></div>
 <p>Contexte par défaut : {data.context_default}. Les réglages se modifient dans <a href="#/configuration">Configuration</a> et <a href="#/sources">Sources médicales</a>.</p>
 <details><summary>Préférences documentaires par module</summary><pre className="instruction-text">{JSON.stringify(data.documentary_preferences||{},null,2)}</pre></details>
 <details><summary>Profondeur et contexte</summary>{Object.entries(data.depth_instructions||{}).map(([k,v])=><p key={k}><strong>{k}</strong> — {v}</p>)}{Object.entries(data.context_instructions||{}).map(([k,v])=><p key={k}><strong>{k}</strong> — {v}</p>)}</details>
 </div>}</section>
}
