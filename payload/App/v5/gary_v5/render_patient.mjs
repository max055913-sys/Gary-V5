// Rendu canonique depuis le brouillon de la SQLite, jamais depuis du HTML client.
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createRequire} from 'node:module';
const requireLocal=createRequire(import.meta.url);
process.env.PLAYWRIGHT_BROWSERS_PATH=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../runtime/browser');
function prerequisite(code){process.exit(code)}
let build,chromium;
try{
 ({build}=requireLocal('esbuild'));
 requireLocal.resolve('react');
 requireLocal.resolve('react-dom/server');
}catch{prerequisite(21)}
try{
 const configured=process.env.GARY_PDF_PLAYWRIGHT;
 const entry=configured?path.resolve(configured):requireLocal.resolve('playwright',{paths:[path.dirname(fileURLToPath(import.meta.url)),path.dirname(path.dirname(process.execPath))]});
 ({chromium}=requireLocal(entry));
 if(!chromium?.launch)prerequisite(22);
}catch{prerequisite(22)}
let input='';for await(const part of process.stdin)input+=part;
const {directory,draft}=JSON.parse(input),root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const code=`import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';import PatientDocument from './PatientDocument.jsx';export function render(draft){const version=draft.versions.at(-1);const approved=draft.validation?.revision===version.revision&&draft.validation.text_sha256===version.text_sha256;return renderToStaticMarkup(<PatientDocument draft={draft} approved={approved} exporting/>);}`;
const built=await build({stdin:{contents:code,loader:'jsx',resolveDir:path.join(root,'frontend')},bundle:true,write:false,platform:'node',format:'cjs'});
const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports);
const html=module.exports.render(draft),css=fs.readFileSync(path.join(root,'frontend/shell.css'),'utf8');
fs.writeFileSync(path.join(directory,'document_version.html'),html,{flag:'wx'});
const executablePath=process.env.GARY_PDF_BROWSER;
let browser;
try{
 browser=await chromium.launch({...(executablePath?{executablePath:path.resolve(executablePath)}:{}),headless:true,args:['--disable-background-networking','--disable-component-update']});
}catch{prerequisite(23)}
try{
 const page=await browser.newPage({viewport:{width:794,height:1123},javaScriptEnabled:false});
 await page.route('**/*',r=>r.abort());await page.emulateMedia({media:'print'});
 await page.setContent('<!doctype html><html lang="fr"><meta charset="utf-8"><style>'+css+'@page{size:A4;margin:15mm}.patient-page{width:auto!important;min-height:0!important;padding:0!important}</style><body style="margin:0;background:white">'+html+'</body></html>');
 await page.pdf({path:path.join(directory,'Fiche_patient.pdf'),format:'A4',printBackground:true,margin:{top:0,right:0,bottom:0,left:0}});
}finally{await browser.close()}
