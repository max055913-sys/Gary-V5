import {bibliographyPresentation} from './reference-presentation.mjs';
export const RESULT_SCHEMA='gary_v5_display_result_v1';
export const STATES=['complete','partial','clarification','refusal','technical_error','insufficient_sources'];
// Présentation uniquement : les annotations originales et leurs positions restent intactes.
export function uniqueSources(sources){return sources.filter((s,i,a)=>!s.url||a.findIndex(v=>v.url===s.url)===i)}
export function additionalSources(text,sources){
 const heading=/(?:^|\n)#{1,6}\s+(?:bibliographie|r[ée]f[ée]rences(?: bibliographiques| documentaires)?|sources(?: consult[ée]es)?)\s*:?[ \t]*(?:\n|$)/ig;
 const matches=[...String(text).matchAll(heading)];
 if(!matches.length)return uniqueSources(sources);
 const bibliography=String(text).slice(matches.at(-1).index);
 const urls=new Set([...bibliography.matchAll(/\[[^\]\n]*\]\((https:\/\/[^\s)]+)\)/g)].map(m=>m[1]));
 return uniqueSources(sources).filter(s=>!urls.has(s.url));
}
export function safeURL(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&u.hostname.includes('.')&&!/^\d{1,3}(?:\.\d{1,3}){3}$|^\[/.test(u.hostname)&&!u.hostname.endsWith('.local')&&!u.hostname.endsWith('.localhost')&&!/[\s\\]/.test(value)}catch{return false}}
export function adapt(raw){
 if(raw?.schema==='gary_sol_web_result_v1'){
  if(raw.clinical_validation!==false||typeof raw.text!=='string'||!Array.isArray(raw.fragments)||!Array.isArray(raw.references)||!STATES.includes(raw.status))throw Error('RESULT_CONTRACT_REFUSED');
  return bibliographyPresentation(validate({schema:RESULT_SCHEMA,status:raw.status,provisional:raw.provisional===true,simulation:false,test:raw.test===true,module:raw.module,title:raw.question,summary:raw.text,fragments:raw.fragments,web_state:raw.web_state,sections:[],sources:uniqueSources(raw.references).map((s,i)=>({id:'native-'+i,native_web:true,title:s.title||'Référence',url:s.url,publication_date:null,updated_date:null,accessible:false,limitations:['Citation native : la lecture intégrale du document n’est pas démontrée.'],fictional:false})).concat((Array.isArray(raw.professional_documents)?raw.professional_documents:[]).filter((s,i,a)=>typeof s.url==='string'&&!raw.references.some(r=>r.url===s.url)&&a.findIndex(v=>v.url===s.url)===i).map((s,i)=>({id:'professional-'+i,native_web:false,title:s.title||'Document professionnel consulté',url:s.url,publication_date:null,updated_date:null,accessible:true,limitations:['Passages DOM consultés le '+s.acquired_at+'. Périmètre partiel ; aucune validation clinique.'],fictional:false}))),warnings:[...(raw.warnings||[]),'Revue médicale requise. Aucun usage thérapeutique autonome.'],missing_profile:[]}));
 }
 if(raw?.schema==='gary_luna_route_c_v1')return {schema:RESULT_SCHEMA,status:'clarification',simulation:false,preparation:true,module:raw.module||'AUTO',title:raw.question||'Routage AUTO',summary:raw.status==='routed'?'Module établi par une décision Luna reconnue. La génération Sol nécessite une autorisation distincte.':raw.status==='clarification'?'Une clarification est nécessaire avant de sélectionner un module.':'Le routage Luna est préparé ; aucun appel réel n’est activé.',sections:[],sources:[],warnings:['Aucune réponse médicale générée.'],missing_profile:[]};
 if(raw?.schema==='gary_v5_generation_display_v1'){
  if(raw.clinical_validation!==false||!['partial','refusal','technical_error'].includes(raw.status)||typeof raw.text!=='string')throw Error('RESULT_CONTRACT_REFUSED');
  return validate({schema:RESULT_SCHEMA,status:raw.status,simulation:false,test:raw.test===true,module:raw.module,title:raw.question,summary:raw.text,sections:[],sources:(raw.references||[]).map((s,i)=>({id:'ref-'+i,title:s.title||'Référence',url:s.url,publication_date:s.publication_date||null,updated_date:null,accessible:false,limitations:['Référence fournie, non vérifiée indépendamment.'],fictional:false})),warnings:['Réponse incomplète, refusée ou indisponible. Aucun nouvel appel automatique. Revue médicale nécessaire.'],missing_profile:[]});
 }
 if(raw?.schema==='gary_v5_prepared_v1'&&raw.status==='routing_error')return {schema:RESULT_SCHEMA,status:'technical_error',simulation:false,preparation:true,module:'AUTO',title:'Échec technique du routage AUTO',summary:raw.message,sections:[],sources:[],warnings:['Aucune relance automatique.'],missing_profile:[]};
 if(raw?.schema==='gary_v5_prepared_v1')return {schema:RESULT_SCHEMA,status:raw.status==='clarification'?'clarification':'partial',simulation:false,preparation:true,module:raw.module,title:raw.question,summary:raw.message,sections:[],sources:[],warnings:['Aucune réponse médicale générée.'],missing_profile:[]};
 if(raw?.schema!=='gary_v5_result_v1'||raw.clinical_validation!==false||!Array.isArray(raw.references)||typeof raw.text!=='string')throw Error('RESULT_CONTRACT_REFUSED');
 return validate({schema:RESULT_SCHEMA,status:'complete',simulation:false,test:raw.test===true,module:raw.module,title:raw.question,summary:raw.text,sections:[],sources:raw.references.map((s,i)=>({id:'ref-'+i,title:s.title||'Référence',url:s.url,publication_date:null,updated_date:null,accessible:false,limitations:['Accessibilité et contenu non vérifiés indépendamment.'],fictional:false})),warnings:['Revue médicale requise. Aucun usage thérapeutique autonome.'],missing_profile:[]});
}
export function validate(value){if(value?.schema!==RESULT_SCHEMA||!STATES.includes(value.status)||value.simulation!==false||!Array.isArray(value.sources)||!Array.isArray(value.sections)||!Array.isArray(value.warnings))throw Error('DISPLAY_CONTRACT_INVALID');const ids=new Set(value.sources.map(s=>s.id));for(const s of value.sections)if(!Array.isArray(s.citation_ids)||s.citation_ids.some(id=>!ids.has(id)))throw Error('DISPLAY_CITATION_INVALID');return value}
