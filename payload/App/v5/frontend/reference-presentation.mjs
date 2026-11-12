// Présentation documentaire uniquement ; le texte et les preuves bruts restent intacts.
export function referenceURL(value){try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password)return value;for(const key of [...u.searchParams.keys()])if(/^utm_/i.test(key)||['gclid','fbclid','msclkid'].includes(key.toLowerCase()))u.searchParams.delete(key);return u.href.replaceAll('(','%28').replaceAll(')','%29')}catch{return value}}
const LINKS=/\[([^\]\n]+)\]\((https:\/\/[^\s)]+)\)/g;
export function bibliographyPresentation(result){
 const sources=[];const numbers=new Map();
 for(const s of result.sources){const url=referenceURL(s.url);if(url&&numbers.has(url))continue;const number=sources.length+1;if(url)numbers.set(url,number);sources.push({...s,original_url:s.url,url,number})}
 const raw=result.summary;const headings=[...raw.matchAll(/^#{1,6}\s+(?:\d+[.)]?\s*)?(?:sources(?: consultées(?: et dates connues)?)?|bibliographie|références(?: bibliographiques| documentaires)?)\s*:?[ \t]*$/gim)];
 let last=headings.at(-1);let text=raw,unlinked=[];
 if(last)for(let i=headings.length-2;i>=0;i--){const between=raw.slice(headings[i].index+headings[i][0].length,last.index);if(/^#{1,6}\s/m.test(between))break;last=headings[i]}
 const suffix=last?raw.slice(last.index+last[0].length).replace(/^#{1,6}\s+(?:\d+[.)]?\s*)?(?:sources(?: consultées(?: et dates connues)?)?|bibliographie|références(?: bibliographiques| documentaires)?)\s*:?[ \t]*$/gim,''):'';
 if(last&&!/^#{1,6}\s/m.test(suffix)){
  text=raw.slice(0,last.index).trimEnd();
  for(const line of suffix.split('\n').map(v=>v.trim()).filter(Boolean)){
   const links=[...line.matchAll(LINKS)];
   if(links.length===1){const link=links[0],url=referenceURL(link[2]);let source=sources.find(s=>s.url===url);
    if(!source){source={id:'bibliography-'+sources.length,url,title:link[1],number:sources.length+1,limitations:[]};sources.push(source);numbers.set(url,source.number)}
    const content=line.replace(/^[-*+]\s+/,'').replace(/\(?\b(?:date|année) inconnue\b\)?/gi,'').trim();
    // Une notice garde les mots et réserves de la source ; seul son lien explicite change de place.
    let notice=content.replace(link[0],'').replace(/\(\s*\)/g,'').trim();
    // Le titre peut être en italique ; ne pas choisir une année en gras plus loin.
    const title=notice.match(/\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/);
    notice=title?notice.replace(title[0],'['+(title[1]||title[2])+']('+url+')'):content.replace(link[0],'['+link[1]+']('+url+')');
    if(!source.notices)source.notices=[];if(!source.notices.includes(notice))source.notices.push(notice);
   }else unlinked.push((links.length?'':'Référence sans lien fourni : ')+line.replace(/^[-*+]\s+/,''));
  }
 }
 let offset=0;const annotations=[];
 for(const f of result.fragments||[]){for(const a of f.annotations||[]){const c=a.original;annotations.push({...a,citation_number:numbers.get(referenceURL(c?.url))||a.citation_number,original:c?{...c,start_index:c.start_index+offset,end_index:c.end_index+offset}:c})}offset+=Array.from(f.text).length+1}
 const fragments=result.fragments?[{text,annotations:annotations.filter(a=>a.original?.end_index<=Array.from(text).length)}]:undefined;
 return {...result,sources,presentation_text:text,presentation_fragments:fragments,bibliography_unlinked:unlinked};
}
export function citationText(text,annotations=[],references=[]){
 const chars=Array.from(String(text)),links=[...String(text).matchAll(LINKS)],markers=new Map();
 const range=m=>[Array.from(String(text).slice(0,m.index)).length,Array.from(String(text).slice(0,m.index+m[0].length)).length];
 for(const a of annotations){const c=a.original;if(!a.position_valid||!c||!Number.isInteger(c.end_index)||c.end_index>chars.length||!Number.isInteger(a.citation_number))continue;
  // Pas d'insertion dans un lien Markdown existant : cela brisait les liens imbriqués.
  if(links.some(m=>referenceURL(m[2])===referenceURL(c.url)&&range(m)[0]<=c.end_index&&range(m)[1]>=c.start_index))continue;
  let end=c.end_index;for(const m of links){const [start,finish]=range(m);if(start<end&&end<finish)end=finish}
  const label=' ['+a.citation_number+']('+referenceURL(c.url)+')';if(!(markers.get(end)||'').includes(label))markers.set(end,(markers.get(end)||'')+label);
 }
 let value=chars.map((c,i)=>c+(markers.get(i+1)||'')).join('');
 return value.replace(LINKS,(whole,label,url)=>{const clean=referenceURL(url);const matching=annotations.find(a=>a.position_valid&&referenceURL(a.original?.url)===clean),reference=references.find(s=>s.url===clean);let domain=false;try{domain=new URL(clean).hostname===label}catch{};return '['+(domain&&(reference||matching)?reference?.number||matching.citation_number:label)+']('+clean+')'});
}
