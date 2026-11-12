import React from 'react';
import Markdown from './Markdown.jsx';
const DRAFT_NOTICE='Brouillon — à faire valider par votre médecin avant remise au patient';
function patientText(source){
 const kept=[];
 let excluded=0;
 for(const line of source.split(/\r?\n/)){
  const heading=line.match(/^(#{1,6})\s+(.+)$/);
  const label=(heading?.[2]??line).trim().replace(/^\*{1,2}|\*{1,2}$/g,'').trim();
  if(excluded&&(!heading||heading[1].length>excluded))continue;
  excluded=0;
  if(heading&&/^(?:sources(?: consultées)?|références(?: documentaires(?: de la fiche)?| bibliographiques)?|bibliographie|note au médecin)\s*[:—-]?\s*$/i.test(label)){
   excluded=heading[1].length;continue;
  }
  if(!heading&&/^note au médecin\s*(?:[:—–-]|$)/i.test(label))continue;
  const notice=label.replace(/^>\s*/,'').replace(/\*{1,2}/g,'').replace(/\s+/g,' ').replace(/\.$/,'');
  if(notice===DRAFT_NOTICE)continue;
  if(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line))continue;
  kept.push(line);
 }
 const citation='\\[[a-z0-9.-]+\\.[a-z]{2,}\\]\\(https?://[^\\s)]+\\)';
 const strip=new RegExp('\\(\\s*'+citation+'(?:\\s*[,;]\\s*'+citation+')*\\s*\\)|'+citation,'gi');
 const result=kept.join('\n').replace(strip,'').trim();
 if(!result||/https?:\/\/|【[^】]*】|\[\d+(?:\s*[,–-]\s*\d+)*\]|(?:^|\n)\s*(?:[*#]+\s*)?(?:note au médecin|sources consultées|références documentaires|bibliographie)\b/i.test(result))throw Error('PATIENT_PRESENTATION_REVIEW_REQUIRED');
 return result;
}
export default function PatientDocument({draft,approved=false,exporting=false}){
 if(exporting&&!approved)throw Error('DRAFT_NOT_APPROVED');
 let content;
 try{content=patientText(draft.versions.at(-1).text)}
 catch(error){if(exporting)throw error;return <p role="alert">Vérifiez les références ou notes internes dans le brouillon avant l’export.</p>}
 const firstTitle=content.match(/^#\s+(.+)$/m)?.[1];
 return <article className="patient-page" style={{background:'#fff',color:'#111',width:'210mm',minHeight:'297mm',padding:'18mm',boxSizing:'border-box',fontFamily:'Arial, sans-serif',fontSize:'11pt',lineHeight:1.5}}>
  {!approved&&<p role="status">{DRAFT_NOTICE}.</p>}
  {!firstTitle&&<h1>{draft.title}</h1>}<Markdown text={content}/>
 </article>
}
