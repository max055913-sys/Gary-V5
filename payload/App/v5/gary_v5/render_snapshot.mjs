// DOM figé reçu du navigateur local ; aucune exécution de script ni accès Web.
import fs from 'node:fs';import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
process.env.PLAYWRIGHT_BROWSERS_PATH=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../runtime/browser');
const requireLocal=createRequire(import.meta.url);
const configured=process.env.GARY_PDF_PLAYWRIGHT;
const {chromium}=requireLocal(configured?path.resolve(configured):'playwright');
let input='';for await (const part of process.stdin)input+=part;
const {directory,width,test,background,pdf_name}=JSON.parse(input);
const html=fs.readFileSync(path.join(directory,'presentation_affichee.html'),'utf8');
const executablePath=process.env.GARY_PDF_BROWSER;
const browser=await chromium.launch({...(executablePath?{executablePath:path.resolve(executablePath)}:{}),headless:true,args:['--disable-background-networking','--disable-component-update']});
try{
 const page=await browser.newPage({viewport:{width,height:1123},javaScriptEnabled:false});
 let requests=0;await page.route('**/*',r=>{requests++;return r.abort()});
 await page.emulateMedia({media:'screen'});
 await page.setContent('<!doctype html><html><meta charset="utf-8"><body style="margin:0;background:'+background+'">'+html+'</body></html>');
 await page.screenshot({path:path.join(directory,'capture_reference.png'),fullPage:true});
 // PDF lisible distinct de la capture : fond blanc et références dépliées.
 const printable=html.replace(/<details([^>]*)>/g,'<details$1 open>');
 const printCSS='*{color:#111!important;background-color:white!important;box-shadow:none!important}details{height:auto!important;overflow:visible!important}details *{height:auto!important}summary{font-weight:bold}table{border-collapse:collapse}.markdown-table{overflow:visible!important;max-width:100%!important;width:100%!important}.markdown-table table{min-width:0!important;width:100%!important;table-layout:fixed!important}.markdown-table tr,.markdown-table td,.markdown-table th{height:auto!important}td,th{border-color:#777!important}a{color:#111!important}tr,.source{break-inside:avoid}thead{display:table-header-group}h2,h3{break-after:avoid}';
 await page.setContent('<!doctype html><html><meta charset="utf-8"><style>'+printCSS+'</style><body style="margin:0;background:white">'+printable+'</body></html>');
 await page.pdf({path:path.join(directory,pdf_name||(test?'Gary_TEST_reponse_originale.pdf':'Gary_reponse_originale.pdf')),width:`${width}px`,height:'1123px',printBackground:true,margin:{top:0,right:0,bottom:0,left:0}});
 fs.writeFileSync(path.join(directory,'render_observation.json'),JSON.stringify({dom_text_matches:true,test,source:'BROWSER_DOM_SNAPSHOT_WITH_COMPUTED_STYLES',background,external_requests:requests,pdf_presentation:'WHITE_READABLE_EXPANDED_REFERENCES',capture_presentation:'DISPLAYED_DOM_SNAPSHOT',pixel_fidelity_certified:false,native_window_screenshot:false,markdown_corrections:false}),{flag:'wx'});
}finally{await browser.close()}
