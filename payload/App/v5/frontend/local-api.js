export async function localAPI(path,data){
 const session=await fetch('/api/windows/session');if(!session.ok)throw Error('SESSION_UNAVAILABLE');
 const token=(await session.json()).token;
 const reply=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'X-Gary-Session':token,...(data===undefined?{}:{'Content-Type':'application/json'})},...(data===undefined?{}:{body:JSON.stringify(data)})});
 const result=await reply.json();if(!reply.ok)throw Error(result.error||'LOCAL_OPERATION_REFUSED');
 return data===undefined?result:result.result;
}
export async function localBlob(path){
 const token=(await(await fetch('/api/windows/session')).json()).token;
 const r=await fetch(path,{headers:{'X-Gary-Session':token}});if(!r.ok)throw Error('DOWNLOAD_REFUSED');
 return r.blob();
}
export async function localDownload(path,name){
 const url=URL.createObjectURL(await localBlob(path)),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
}
export function patientPdfFilename(title){
 const subject=(typeof title==='string'?title:'').normalize('NFD')
  .replace(/\p{M}/gu,'').replace(/[<>:"/\\|?*\x00-\x1f]/g,'')
  .replace(/\s+/g,'_').replace(/[^\p{L}\p{N}_-]/gu,'')
  .replace(/^[_-]+|[_-]+$/g,'').slice(0,100).replace(/[_-]+$/g,'');
 return 'Fiche_'+(subject||'patient')+'.pdf';
}
