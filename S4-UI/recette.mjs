import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';

const {chromium}=await import(pathToFileURL(process.env.GARY_PLAYWRIGHT));
const dist=process.argv[2]??fileURLToPath(new URL('../payload/App/v5/dist/',import.meta.url));
const origin='http://127.0.0.1:8785';
const examples=[
 'AUTO Hypercalcémie','DIAG Douleur thoracique aiguë','PATH Hypertension artérielle',
 'TTT Amoxicilline','SUIVI Femme 66 ans diabète type II','PED Nourrisson de 4 mois',
 'PREG Suivi grossesse 24 SA','ADM Condition rechute accident de travail','FICH Dermatite atopique',
];
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-background-networking','--disable-component-update']});
try{
 const page=await browser.newPage({viewport:{width:1240,height:820}});
 let configured=false, enabled=false, external=0, dialogs=0, saves=0;
 const mockKey='S4UI-fictitious-fixture-only';
 page.on('dialog',async dialog=>{dialogs++;await dialog.dismiss()});
 await page.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.origin!==origin){external++;return route.abort()}
  const p=url.pathname;
  if(p==='/api/health')return route.fulfill({json:{transport:configured&&enabled}});
  if(p==='/api/windows/session')return route.fulfill({json:{managed:true,token:'fixture-session'}});
  if(p==='/api/openai/key/status')return route.fulfill({json:{configured,api_enabled:enabled}});
  if(p==='/api/openai/key'&&req.method()==='POST'){
   assert.equal(req.headers()['x-gary-session'],'fixture-session');
   assert.equal(req.postDataJSON().key,mockKey);saves++;configured=true;
   return route.fulfill({json:{result:{configured:true}}});
  }
  if(p==='/api/local/updates')return route.fulfill({json:{version:'5.0.0-rc.1',automatic:true,configured:false,period_days:7}});
  if(p.startsWith('/api/')){
   assert.equal(req.method(),'GET');
   return route.fulfill({status:404,json:{}});
  }
  const file=p==='/'?'index.html':p.slice(1);
  assert.ok(file==='index.html'||file.startsWith('assets/'));
  const type={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png'}[path.extname(file)];
  return route.fulfill({body:await readFile(path.join(dist,file)),contentType:type});
 });
 const go=async name=>page.evaluate(n=>{location.hash='/'+n},name);
 await page.goto(origin+'/#/recherche');
 const notice=page.getByText('API OpenAI non configurée — Génération indisponible',{exact:true});
 await notice.waitFor();
 await page.getByRole('link',{name:"Voir le mode d'emploi"}).click();
 const heading=page.getByRole('heading',{name:'Mise en route',exact:true});
 await heading.waitFor();
 assert.equal(await heading.evaluate(el=>el===document.activeElement&&!el.closest('details')&&el.parentElement.previousElementSibling.tagName==='H1'),true);
 assert.equal(await page.getByRole('link',{name:'OpenAI Platform',exact:true}).getAttribute('href'),'https://platform.openai.com/');
 assert.equal(await page.getByRole('link',{name:'gestion des clés API'}).getAttribute('href'),'https://platform.openai.com/api-keys');
 await page.getByText('L’API est facturée séparément de ChatGPT.',{exact:false}).waitFor();
 await page.getByText('Commencez avec un petit budget',{exact:false}).waitFor();
 await page.getByText('Choisir le bon module',{exact:true}).click();
 assert.deepEqual(await page.locator('.guide-modules tbody code').allTextContents(),examples);
 await page.getByText('La génération par Sol peut être facturée',{exact:false}).waitFor();
 assert.equal(await page.getByText('Comprendre les réponses et les sources',{exact:true}).count(),0);
 await page.setViewportSize({width:360,height:760});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await go('configuration');
 await page.getByText('Clé API non configurée',{exact:true}).waitFor();
 await page.getByText('Recherche automatique tous les 7 jours',{exact:true}).waitFor();
 const key=page.getByLabel('Clé API OpenAI',{exact:true});
 for(let i=0;i<2;i++){
  await key.fill(mockKey);
  await page.getByRole('button',{name:'Enregistrer la clé',exact:true}).click();
  await page.getByText('Clé API enregistrée',{exact:false}).waitFor();
  await page.waitForFunction(()=>document.querySelector('input[type=password]').value==='');
  assert.equal(await page.getByText('********',{exact:true}).isVisible(),true);
  assert.equal((await page.locator('body').innerText()).includes(mockKey),false);
 }
 await go('recherche');
 await notice.waitFor();
 enabled=true;
 await notice.waitFor({state:'hidden',timeout:8000});
 assert.equal(saves,2);assert.equal(external,0);assert.equal(dialogs,0);
 console.log('Chrome : accueil, lien et focus, guide et 9 exemples, mobile, masque, remplacement et actualisation : OK');
}finally{await browser.close()}
