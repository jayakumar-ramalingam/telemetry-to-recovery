/* Records only a fresh headless browser containing this local synthetic demo.
 * No desktop capture, existing profile, microphone, or private browser tabs.
 */
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.DEMO_URL || 'http://127.0.0.1:8765';
const out = path.resolve(process.env.DEMO_RECORD_DIR || 'recordings');
const backups = path.join(out,'screenshots');
await fs.mkdir(backups,{recursive:true});
const video = path.join(out,'Telemetry_to_Recovery_Demo.mp4');
const candidateVideo = path.join(out,'Telemetry_to_Recovery_Demo.partial.mp4');
try { await fs.access(video); throw Error(`Recording already exists: ${video}. Choose another directory or move the previous recording.`); }
catch(e) { if(e.code!=='ENOENT')throw e; }
const browser = await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
const context = await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const page = await context.newPage();
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
let encoder, timer, session;
try {
  await page.goto(base);
  await page.locator('#headline').filter({hasText:/./}).waitFor();
  await page.selectOption('#scenario','memory');
  await page.getByRole('button',{name:'New run',exact:true}).click();
  await page.getByRole('button',{name:'Inject release + fault',exact:true}).waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.body.classList.contains('busy'), null, {timeout:150000});
  const initial = await (await page.request.get(`${base}/api/state`)).json();
  const modelMode = initial.ai_required === true;
  const provider = initial.ai_config?.provider || "rules";
  if(modelMode && (!initial.ai_config?.configured || !initial.ai_config?.sdk_available))throw Error('The model is not configured. Complete LOCAL_SETUP.md or BEDROCK_SETUP.md.');
  if(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight))throw Error('Recording layout overflows viewport');
  session=await context.newCDPSession(page);
  let frame=await page.screenshot({type:'jpeg',quality:92});
  session.on('Page.screencastFrame',event=>{
    frame=Buffer.from(event.data,'base64');
    session.send('Page.screencastFrameAck',{sessionId:event.sessionId}).catch(()=>{});
  });
  await session.send('Page.startScreencast',{format:'jpeg',quality:92,maxWidth:1920,maxHeight:1080,everyNthFrame:1});
  encoder=spawn(process.env.FFMPEG || 'ffmpeg',[
    '-hide_banner','-loglevel','error','-f','image2pipe','-framerate','10','-vcodec','mjpeg','-i','pipe:0',
    '-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',candidateVideo
  ],{stdio:['pipe','ignore','pipe']});
  let encodingError='';
  encoder.stderr.on('data',d=>encodingError+=d.toString());
  const finished=new Promise((resolve,reject)=>{
    encoder.on('error',reject);encoder.on('close',code=>code===0?resolve():reject(Error(encodingError||`FFmpeg exit ${code}`)));
  });
  let frames=0;
  timer=setInterval(()=>{if(!encoder.stdin.destroyed && !encoder.stdin.writableNeedDrain){encoder.stdin.write(frame);frames++;}},100);
  const chapters=[];
  async function hold(name,seconds,caption){
    if(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight || document.documentElement.scrollWidth>innerWidth))throw Error(`Recording layout overflows at ${name}`);
    chapters.push({name,start_seconds:frames/10,caption});
    await page.screenshot({path:path.join(backups,`${String(chapters.length).padStart(2,'0')}-${name}.png`)});
    console.log(`${name}: ${seconds}s`);
    await new Promise(r=>setTimeout(r,seconds*1000));
  }
  async function click(label){
    await page.getByRole('button',{name:label,exact:true}).click();
    await page.waitForFunction(()=>!document.body.classList.contains('busy'), null, {timeout:150000});
    if(!await page.locator('#error').isHidden())throw Error(await page.locator('#error').textContent());
  }
  await hold('healthy-baseline',22,'Synthetic workload. Real local agent rules and persisted incident events.');
  await click('Inject release + fault');
  await hold('incident',28,'Worker v2 appears before growing memory, restarts, and aging queued work.');
  await click('Collect incident evidence');
  await hold('preserve-evidence',22,'Preserve baseline, changes, and observations. Exclude injector fault labels.');
  await click('Run diagnostic agents');
  if(modelMode){
    const diagnosis = await (await page.request.get(`${base}/api/state`)).json();
    if(!diagnosis.ai_report?.model_invoked || !diagnosis.ai_report?.validated || diagnosis.stage!=='diagnosed')throw Error('No accepted model diagnosis. A successful-model recording cannot be generated.');
    await hold('model-response',25,'Actual model response with supplied evidence and runbook references. No execution tools.');
    await page.getByRole('tab',{name:'Investigation',exact:true}).click();
  }
  await hold('investigation',35,'Compare competing explanations. A leading hypothesis is not proof of the code defect.');
  await click('Build + evaluate plan');
  await hold('action-contract',25,'Admit one bounded rollback proposal. Evidence, compatibility, target, and revision must match.');
  await click('Why not scale out?');
  await hold('denied-alternative',22,'The alternative fails policy. The linear capacity estimate is illustrative, not calibrated.');
  await click('Approve this recovery');
  await hold('exact-plan-approval',18,'Human approval is bound to the exact plan. The executor rechecks preconditions.');
  await click('Execute approved rollback');
  await hold('action-completed',20,'The simulated actuator completed the rollback. Recovery is not yet verified.');
  await click('Observe + verify recovery');
  await page.getByRole('tab',{name:'Investigation',exact:true}).click();
  await hold('recovery-verified',30,'120 scenario seconds observed. The final 30 seconds meet all five workload checks.');
  await click('Retry the same action');
  await hold('duplicate-suppressed',14,'Return the original action receipt. Do not apply a second mutation.');
  await click('Replay recorded history');
  await hold('replay-without-effects',18,'Reconstruct recorded state from events. Replay performs zero recovery side effects.');
  await page.getByRole('tab',{name:'Event journal',exact:true}).click();
  await hold('event-journal',14,'The journal links evidence, proposal, approval, action, and verification.');
  const success=await (await page.request.get(`${base}/api/export`)).json();
  await fs.writeFile(path.join(out,'successful-incident.json'),JSON.stringify(success,null,2));
  await page.selectOption('#scenario','gap');
  await click('New run');
  await hold('second-scenario',4,'Counterexample: the same symptom, but incomplete memory observations.');
  await click('Inject release + fault');
  await hold('missing-memory',5,'Missing evidence is not the same as a healthy metric.');
  await click('Collect incident evidence');
  await hold('incomplete-window',4,'The investigation must preserve and report the gap.');
  await click('Run diagnostic agents');
  if(modelMode){
    const refusalState = await (await page.request.get(`${base}/api/state`)).json();
    if(!refusalState.ai_report?.model_invoked || !refusalState.ai_report?.validated || refusalState.stage!=='stopped')throw Error('The incomplete-evidence model run was not validated and safely stopped. Preserve this as a failed attempt, not a completed demo.');
  }
  await hold('stop-and-escalate',25,'Insufficient evidence blocks recovery. Escalate without a mutation.');
  const refusal=await (await page.request.get(`${base}/api/export`)).json();
  await fs.writeFile(path.join(out,'refused-incident.json'),JSON.stringify(refusal,null,2));
  clearInterval(timer);timer=null;
  await session.send('Page.stopScreencast');
  encoder.stdin.end();
  await finished;
  if(errors.length)throw Error(errors.join('\n'));
  for(let i=0;i<chapters.length;i++)chapters[i].end_seconds=chapters[i+1]?.start_seconds??frames/10;
  await fs.writeFile(path.join(out,'chapters.json'),JSON.stringify({duration_seconds:frames/10,disclosure:modelMode?'Silent recording with actual read-only model investigation and synthetic workload/actuator; not a research benchmark.':'Silent recording of explicit deterministic baseline; no LLM or live Kubernetes.',provider,chapters},null,2));
  function stamp(s){const ms=Math.round(s*1000);return `${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`;}
  await fs.writeFile(path.join(out,'Telemetry_to_Recovery_Demo.srt'),chapters.map((c,i)=>`${i+1}\n${stamp(c.start_seconds)} --> ${stamp(c.end_seconds)}\n${c.caption}\n`).join('\n'));
  await fs.rename(candidateVideo,video);
  console.log(JSON.stringify({video,duration_seconds:frames/10,chapters:chapters.length,passed:true}));
} finally {
  if(timer)clearInterval(timer);
  if(encoder && !encoder.stdin.destroyed)encoder.stdin.end();
  await browser.close();
}
