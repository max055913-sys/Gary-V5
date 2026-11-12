import React from 'react';
import {safeURL} from './result-contract.mjs';
import {citationText} from './reference-presentation.mjs';

// Sous-ensemble Markdown explicite, sans HTML brut, plugin, image distante ou eval.
function inline(text,key='t'){
 const pattern=/(!?\[[^\]\n]+\]\([^\s)]+\)|\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\*[^*\n]+\*)/g;
 const out=[];let start=0,match;
 while((match=pattern.exec(text))){if(match.index>start)out.push(text.slice(start,match.index));const v=match[0],k=key+match.index;
  if(v.startsWith('!['))out.push(<span key={k}>{v}</span>);
  else if(v.startsWith('[')){const m=v.match(/^\[([^\]]+)\]\((.*)\)$/);out.push(safeURL(m[2])?<a key={k} href={m[2]} target="_blank" rel="noopener noreferrer">{m[1]}</a>:<span key={k}>{v}</span>)}
  else if(v.startsWith('**')||v.startsWith('__'))out.push(<strong key={k}>{v.slice(2,-2)}</strong>);
  else if(v.startsWith('`'))out.push(<code key={k}>{v.slice(1,-1)}</code>);
  else out.push(<em key={k}>{v.slice(1,-1)}</em>);
  start=pattern.lastIndex;
 }
 if(start<text.length)out.push(text.slice(start));return out;
}
function cells(line){return line.trim().replace(/^\|/,'').replace(/\|$/,'').split(/(?<!\\)\|/).map(v=>v.trim().replaceAll('\\|','|'))}
export default function Markdown({text,annotations=[],references=[]}){
 const presented=citationText(text,annotations,references);
 const lines=presented.replace(/\r\n?/g,'\n').split('\n'),out=[];let i=0;
 while(i<lines.length){const line=lines[i];if(!line.trim()){i++;continue}
  if(/^\s*```/.test(line)){const code=[];i++;while(i<lines.length&&!/^\s*```/.test(lines[i]))code.push(lines[i++]);if(i<lines.length)i++;out.push(<pre key={i}><code>{code.join('\n')}</code></pre>);continue}
  const heading=line.match(/^(#{1,6})\s+(.+?)(?:\s+#+)?$/);if(heading){const Tag='h'+Math.min(heading[1].length+1,6);out.push(<Tag key={i}>{inline(heading[2],String(i))}</Tag>);i++;continue}
  if(i+1<lines.length&&line.includes('|')&&/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i+1])){
   const headers=cells(line),rows=[];i+=2;while(i<lines.length&&lines[i].includes('|')&&lines[i].trim())rows.push(cells(lines[i++]));
   // Grille irrégulière : conserver les cellules excédentaires, sans les fusionner par supposition.
   const width=Math.max(headers.length,...rows.map(r=>r.length));
   out.push(<div className="markdown-table" key={'table'+i}><table><thead><tr>{Array.from({length:width},(_,n)=><th key={n}>{inline(headers[n]||'')}</th>)}</tr></thead><tbody>{rows.map((r,n)=><tr key={n}>{Array.from({length:width},(_,c)=><td key={c}>{inline(r[c]||'')}</td>)}</tr>)}</tbody></table></div>);continue
  }
  const list=line.match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);if(list){const ordered=/\d/.test(list[1]),items=[];while(i<lines.length){const m=lines[i].match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);if(!m||/\d/.test(m[1])!==ordered)break;items.push({text:m[2],ordinal:ordered?parseInt(m[1],10):undefined});i++}const Tag=ordered?'ol':'ul';out.push(<Tag key={i} start={ordered?parseInt(list[1],10):undefined}>{items.map((v,n)=><li key={n} value={v.ordinal}>{inline(v.text)}</li>)}</Tag>);continue}
  if(/^>\s?/.test(line)){const block=[];while(i<lines.length&&/^>/.test(lines[i]))block.push(lines[i++].replace(/^>\s?/,''));out.push(<blockquote key={i}>{inline(block.join('\n'))}</blockquote>);continue}
  const paragraph=[line];i++;while(i<lines.length&&lines[i].trim()&&!/^(#{1,6}\s|\s*[-+*]\s|\s*\d+[.)]\s|```|>)/.test(lines[i])&&!(i+1<lines.length&&lines[i].includes('|')&&/^\s*\|?\s*:?-{3}/.test(lines[i+1])))paragraph.push(lines[i++]);
  out.push(<p key={i}>{inline(paragraph.join('\n'),String(i))}</p>);
 }
 return <div className="medical-markdown" data-rendered-response>{out}</div>;
}
