import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.DEMO_URL || 'http://127.0.0.1:8768';
const out = path.resolve('qa-local/ui');
await fs.mkdir(out,{recursive:true});
const browser = await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
const page = await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.goto(base);
await page.locator('#headline').filter({hasText:/./}).waitFor();
await page.selectOption('#scenario','memory');
await page.getByRole('button',{name:'New run',exact:true}).click();
await page.locator('#phase').filter({hasText:'BASELINE'}).waitFor();
async function snap(name){await page.screenshot({path:path.join(out,`${name}.png`)});}
await snap('01-baseline');
for(const [label,name] of [['Inject release + fault','02-incident'],['Collect incident evidence','03-evidence'],['Run diagnostic agents','04-diagnosis'],['Build + evaluate plan','05-plan']]){
  await page.getByRole('button',{name:label,exact:true}).click();
  await page.waitForFunction(()=>!document.body.classList.contains('busy'), null, {timeout:150000});
  if(name==='04-diagnosis'){
    const s=await (await page.request.get(`${base}/api/state`)).json();
    if(s.ai_config.provider!=='ollama'||!s.ai_report?.validated||!s.ai_report?.model_invoked||s.stage!=='diagnosed')throw Error('Actual local model diagnosis not accepted');
  }
  await snap(name);
}
await page.getByRole('button',{name:'Why not scale out?',exact:true}).click();
await page.getByText('Rejected alternative: scale 3 to 9 workers',{exact:true}).waitFor();
await snap('06-denied-alternative');
await page.getByRole('button',{name:'Approve this recovery',exact:true}).click();
await page.getByRole('button',{name:'Execute approved rollback',exact:true}).waitFor();
await snap('07-approved');
await page.getByRole('button',{name:'Execute approved rollback',exact:true}).click();
await page.getByRole('button',{name:'Observe + verify recovery',exact:true}).waitFor();
await snap('08-executed');
await page.getByRole('button',{name:'Observe + verify recovery',exact:true}).click();
await page.getByRole('button',{name:'Retry the same action',exact:true}).waitFor();
await page.getByRole('tab',{name:'Investigation',exact:true}).click();
await snap('09-verified');
await page.getByRole('button',{name:'Retry the same action',exact:true}).click();
await page.getByRole('button',{name:'Replay recorded history',exact:true}).waitFor();
await page.getByRole('button',{name:'Replay recorded history',exact:true}).click();
await page.getByText(/Replay: worker:v1/).waitFor();
await snap('10-replayed');
const exported=await (await page.request.get(`${base}/api/export`)).json();
if(exported.events.filter(e=>e.kind==='change.applied').length!==1)throw Error('Duplicate mutation');
await fs.writeFile(path.join(out,'successful-run.json'),JSON.stringify(exported,null,2));
await page.selectOption('#scenario','gap');
await page.getByRole('button',{name:'New run',exact:true}).click();
await page.getByRole('button',{name:'Inject release + fault',exact:true}).waitFor();
for(const label of ['Inject release + fault','Collect incident evidence','Run diagnostic agents']){
  await page.getByRole('button',{name:label,exact:true}).click();
  await page.waitForFunction(()=>!document.body.classList.contains('busy'), null, {timeout:150000});
}
await page.getByText('STOP: incomplete evidence. No recovery action.',{exact:true}).waitFor();
const stopped=await (await page.request.get(`${base}/api/state`)).json();
if(!stopped.ai_report?.validated||stopped.stage!=='stopped'||stopped.execution)throw Error('Independent evidence checks did not stop recovery');
await snap('11-refusal');
const refusal=await (await page.request.get(`${base}/api/export`)).json();
if(refusal.events.some(e=>e.kind==='change.applied'))throw Error('Refusal path mutated');
await fs.writeFile(path.join(out,'refused-run.json'),JSON.stringify(refusal,null,2));
const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,height:innerHeight,scrollHeight:document.documentElement.scrollHeight}));
if(overflow.scroll>overflow.width)throw Error('Horizontal overflow');
await page.setViewportSize({width:390,height:844});
await snap('12-mobile');
const mobile=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
if(mobile)throw Error('Mobile horizontal overflow');
if(errors.length)throw Error(errors.join('\n'));
await page.selectOption('#scenario','memory');
await page.getByRole('button',{name:'New run',exact:true}).click();
await page.getByRole('button',{name:'Inject release + fault',exact:true}).waitFor();
await browser.close();
console.log(JSON.stringify({passed:true,consoleErrors:errors,desktopLayout:overflow,screenshots:out}));
