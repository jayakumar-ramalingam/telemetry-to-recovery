/* UI checks for the fail-closed, unconfigured Bedrock path. No fake AI provider. */
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.DEMO_URL||'http://127.0.0.1:8766';
const out=path.resolve('qa-bedrock');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
  await page.goto(base);
  await page.locator('#headline').filter({hasText:/./}).waitFor();
  await page.getByRole('button',{name:'New run',exact:true}).click();
  await page.waitForFunction(()=>!document.body.classList.contains('busy'));
  await page.getByRole('tab',{name:'AI investigator',exact:true}).click();
  await page.screenshot({path:path.join(out,'01-bedrock-setup.png')});
  for(const label of ['Inject release + fault','Collect incident evidence','Run diagnostic agents']){
    await page.getByRole('button',{name:label,exact:true}).click();
    await page.waitForFunction(()=>!document.body.classList.contains('busy'));
  }
  await page.getByText('STOP: AI investigation unavailable or rejected.',{exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'02-bedrock-fail-closed.png')});
  const state=await (await page.request.get(`${base}/api/state`)).json();
  if(state.stage!=='stopped'||state.ai_report.validated||state.execution)throw Error('Unconfigured model did not fail closed');
  if(state.ai_report.model_invoked)throw Error('Unconfigured model is incorrectly labeled invoked');
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===1440?900:844});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(`Horizontal overflow at ${width}`);
  }
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({passed:true,mode:'bedrock-unconfigured',modelInvocations:0,consoleErrors:errors}));
}finally{await browser.close();}
