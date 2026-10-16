/* UI reads actual backend state. It never manufactures metrics or approvals. */
let state;
let tab = "investigation";
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clock = (s) => `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`;
const token = document.querySelector('meta[name="demo-token"]').content;
const providerName = () => state?.ai_config?.provider==="ollama"?"Local Llama · Ollama":state?.ai_config?.provider==="bedrock"?"AWS Bedrock":"Rules baseline · no LLM";
const buttons = {
  baseline:["Inject release + fault","next"], incident:["Collect incident evidence","next"],
  evidence:["Run diagnostic agents","next"], diagnosed:["Build + evaluate plan","next"],
  planned:["Approve this recovery","approve"], approved:["Execute approved rollback","execute"],
  executed:["Observe + verify recovery","verify"], verified:["Recovery verified",null], stopped:["Escalated · no further action",null]
};
async function command(path, extra={}) {
  document.body.classList.add("busy"); $("next").disabled = true; $("error").hidden = true;
  if(path==="next" && state?.stage==="evidence" && state.ai_required) $("next").textContent=`Investigating with ${providerName()}…`;
  try {
    const res = await fetch(`/api/${path}`, {method:"POST",headers:{"Content-Type":"application/json","X-Demo-Token":token},body:JSON.stringify({run_id:state?.run_id,...extra})});
    const result=await res.json();
    if(!res.ok){
      if(result.state){state=result.state;tab=state.execution_blocked?"decision":tab;render();}
      throw Error(result.error);
    }
    state=result;
    if(path==="next" && state.stage==="planned") tab="action";
    if(path==="next" && ["diagnosed","stopped"].includes(state.stage) && state.ai_required && state.ai_report) tab="ai";
    if(path==="new") tab="investigation";
    if(path==="challenge-db") tab="decision";
    render();
  } catch(e) {$("error").textContent=e.message; $("error").hidden=false; if(state)renderControls();}
  finally {document.body.classList.remove("busy");if(state)renderControls();}
}
function chart(target,key,max,threshold){
  const values=state.metrics; const W=420,H=64,pad=5;
  const minT=values[0].scenario_s,maxT=Math.max(values.at(-1).scenario_s,60);
  const x=m=>pad+(m.scenario_s-minT)/(maxT-minT)*(W-pad*2);
  const y=v=>H-17-Math.min(max,v)/max*(H-23);
  let segments=[],current=[];
  for(const m of values){if(m[key]===null){if(current.length)segments.push(current);current=[];}else current.push(`${x(m).toFixed(1)},${y(m[key]).toFixed(1)}`);}
  if(current.length)segments.push(current);
  $(target).innerHTML=`<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(key)} over simulated scenario time"><line x1="${pad}" y1="${y(threshold)}" x2="${W-pad}" y2="${y(threshold)}" stroke="var(--line)" stroke-dasharray="4 4"/>${segments.map(a=>`<polyline points="${a.join(" ")}" fill="none" stroke="var(--teal)" stroke-width="2.5"/>`).join("")}<text x="${pad}" y="${H-2}">${clock(minT)}</text><text x="${W-pad}" y="${H-2}" text-anchor="end">${clock(maxT)}</text></svg>`;
}
const checks = items => `<div class="checklist">${items.map(c=>`<div class="check ${c.passed?"":"fail"}"><span class="mark">${c.passed?"✓":"×"}</span><span>${esc(c.name)}</span></div>`).join("")}</div>`;
function aiInvestigation(){
  const config=state.ai_config||{provider:"rules"};
  const report=state.ai_report;
  const books=state.ai_packet?.runbooks||[];
  const left=`<div><h3>Read-only investigator</h3><dl class="contract"><dt>Provider</dt><dd>${esc(providerName())}</dd><dt>Model</dt><dd>${esc(config.model_id||"None")}</dd><dt>Model response</dt><dd>${report?.model_invoked?"Received from model":report?.request_attempted?"Request attempted; no complete response":"Not received"}</dd><dt>Validation</dt><dd>${report?.validated?"Structure + references accepted":report?"Not accepted":"Pending"}</dd><dt>Execution tools</dt><dd>None</dd></dl>${report?.error?`<p class="callout">${esc(report.error)}</p>`:""}<p class="small" style="margin-top:10px">A model citation is not proof. Independent scenario rules and approval still gate every action.</p></div>`;
  let right;
  if(report?.validated){const a=report.analysis;right=`<div><h3>Model proposal: ${esc(a.proposed_action)}</h3><p class="muted">${esc(a.summary)}</p><p class="small" style="margin-top:10px">Evidence ${a.evidence.map(n=>`#${n}`).join(", ")}<br>Runbooks ${a.runbook_refs.map(esc).join(", ")}</p>${state.stage==="stopped"?`<p class="callout">WORKFLOW BLOCKED: accepted JSON is not permission. Independent evidence checks still control recovery.</p>`:""}<p class="callout">Unknown: ${esc(a.unknowns.join(". "))}</p><p class="small" style="margin-top:10px">Recorded model latency ${report.latency_ms} ms · ${report.usage?.inputTokens??"?"} input / ${report.usage?.outputTokens??"?"} output tokens</p></div>`;}
  else{right=`<div><h3>${report?"No model-backed recovery permission":"Evidence + owned guidance"}</h3><p class="muted">${config.provider==="rules"?"This run is explicitly the deterministic baseline. It is not an AI-generated diagnosis.":report?"The model did not supply an accepted response. The workflow stops; it does not silently switch to rules and execute.":"The investigator will receive observation events and locally retrieved service runbooks. Injector labels, approvals, and credentials are excluded."}</p>${books.map(b=>`<div class="evidence-row"><span>${esc(b.id)}</span><span class="small">${esc(b.owner)}</span></div>`).join("")}<p class="small" style="margin-top:10px">Local metadata/keyword retrieval; no hosted vector database. ${config.provider==="bedrock"&&!config.configured?"Set model and region using BEDROCK_SETUP.md.":""}</p></div>`;}
  return `<div class="two-col">${left}${right}</div>`;
}
function investigation(){
  if(state.execution_blocked){
    return `<div class="two-col"><div><h3>Execution blocked by current conditions</h3>${checks(state.execution_policy.checks.filter(c=>!c.passed))}<p class="callout">The approved plan was not executed. No recovery mutation occurred.</p></div><div><h3>Approval is not a guarantee of execution</h3><p class="muted">The executor checked the current state again. Inspect Input &amp; decision to compare the original model context with the later observations.</p><p class="small" style="margin-top:12px">Start a new investigation; do not bypass the failed precondition.</p></div></div>`;
  }
  if(state.stage==="verified" || state.verification){
    return `<div class="two-col"><div><h3>Verification is a separate decision</h3>${checks(state.verification.checks)}<p class="callout">120-second observation window; final 30 seconds must pass all checks.</p></div><div><h3>What the team can explain</h3><div class="evidence-row"><span>Likely cause</span><span>Worker v2 regression</span></div><div class="evidence-row"><span>Authorized action</span><span>Rollback demo/workers</span></div><div class="evidence-row"><span>Revision now serving</span><span>${esc(state.revision)}</span></div><div class="evidence-row"><span>Completed mutations</span><span>1</span></div><p class="small" style="margin-top:10px">The exact code defect remains unproven. The synthetic workload recovered under the recorded intervention.</p>${state.duplicate?`<p class="replay">${esc(state.duplicate)}</p>`:""}${state.replay?`<p class="replay">Replay: ${esc(state.replay.revision)} · ${state.replay.completed_actions} action · ${state.replay.last_queue_age_s} s queue age · 0 side effects</p>`:""}</div></div>`;
  }
  if(state.diagnosis){
    const d=state.diagnosis;
    return `<div class="two-col"><div><h3>Competing hypotheses</h3>${d.hypotheses.map(h=>`<div class="hypothesis"><strong>${esc(h.name)}</strong><span class="verdict">${esc(h.verdict)}</span><span class="reason">${esc(h.why)}</span></div>`).join("")}<p class="small" style="margin-top:12px">Evidence: ${d.evidence.map(n=>`#${n}`).join(", ")} · No model-generated confidence percentage</p></div><div><h3>${d.status==="insufficient_evidence"?"Supervisor: escalate":"Supervisor: a bounded recovery trial"}</h3><p class="muted">${esc(d.summary)}</p><p class="callout">${d.status==="insufficient_evidence"?"Missing evidence blocks execution. No mutation occurred.":"Correlation narrows the investigation. Verification tests whether the intervention helps."}</p><p class="small" style="margin-top:12px">Unknown: ${esc(d.unknowns.join(". "))}.</p></div></div>`;
  }
  const events=state.journal.filter(e=>e.kind==="change.recorded"||e.kind==="telemetry.sample");
  const refs=[events[0],events.find(e=>e.kind==="change.recorded"),events.at(-1)].filter(Boolean);
  return `<div class="two-col"><div><h3>${state.stage==="baseline"?"The workload contract":"Incident evidence window"}</h3><div class="evidence-row"><span>Arrival rate / processing capacity</span><span>${state.metrics.at(-1).input_rps} / ${state.metrics.at(-1).throughput} jobs/s</span></div><div class="evidence-row"><span>Worker restarts</span><span>${state.metrics.at(-1).restarts}</span></div><div class="evidence-row"><span>Database utilization</span><span>${state.metrics.at(-1).db_pct}%</span></div>${refs.map(e=>`<div class="evidence-row"><span>${clock(e.scenario_s)} · ${e.kind==="change.recorded"?"Worker release recorded":e.payload.revision+" observation"}</span><span class="ref">event #${e.seq}</span></div>`).join("")}</div><div><h3>Three roles, one evidence history</h3><div class="agent-list"><div class="agent-row"><b>Detection</b><span>Check workload symptoms against explicit rules.</span></div><div class="agent-row"><b>Reasoning</b><span>Compare release history, resource profile, and dependencies.</span></div><div class="agent-row"><b>Remediation</b><span>Propose an allowlisted action; execute only after policy + approval.</span></div></div><p class="callout">${state.stage==="evidence"?"Agents receive observations and change events—not the injected fault label.":"The workload is simulated. The agents and event journal execute locally."}</p></div></div>`;
}
function action(){
  if(!state.plan) return `<div class="two-col"><div><h3>No recovery proposal yet</h3><p class="muted">Gather evidence and investigate before selecting an action.</p></div><div><h3>Execution boundaries</h3><p class="muted">One allowlisted workload. No shell tool. No arbitrary commands. Human approval is required for the exact plan.</p></div></div>`;
  const p=state.plan;
  const evaluation=state.execution_policy||state.denial||state.policy;
  const heading=state.execution_policy?(state.execution_policy_phase==="preview"?"Current-condition preview":"Executor precondition checks"):state.denial?"Rejected alternative: scale 3 to 9 workers":"Proposal admission checks";
  return `<div class="two-col"><div><h3>Proposed action</h3><dl class="contract"><dt>Action ID</dt><dd>${esc(p.action_id)}</dd><dt>Target</dt><dd>${esc(p.target)}</dd><dt>Operation</dt><dd>rollback · v2 to v1</dd><dt>Expected revision</dt><dd>${esc(p.expected_revision)}</dd><dt>Evidence</dt><dd>${p.evidence_refs.map(n=>`#${n}`).join(", ")}</dd><dt>Approval</dt><dd>${state.approval?"Granted for the exact plan hash":"Required · not yet granted"}</dd><dt>Verification</dt><dd>120 scenario seconds</dd></dl><p class="small">Prior-revision compatibility is declared by this synthetic fixture.</p></div><div><h3>${heading}</h3>${checks(state.denial&&!state.execution_policy?evaluation.checks.filter(c=>!c.passed):evaluation.checks)}${state.condition_change?`<p class="callout">DB pressure changed after approval. The original model input and approved plan are unchanged.</p>`:state.denial?`<p class="callout">A scale-out multiplier is a conservative scenario estimate, not a production capacity model. The rollback proposal is unchanged.</p>`:""}</div></div>`;
}
function inputDecision(){
  const packet=state.ai_packet, report=state.ai_report, analysis=report?.analysis;
  const samples=(packet?.observations||[]).filter(e=>e.kind==="telemetry.sample");
  const atInvestigation=samples.at(-1), current=state.metrics.at(-1);
  const mutations=state.journal.filter(e=>e.kind==="change.applied").length;
  const evaluation=state.execution_policy||state.policy;
  const rule=state.rule_diagnosis;
  let label="AWAITING INVESTIGATION", tone="pending";
  if(state.execution_blocked){label="EXECUTION BLOCKED";tone="blocked";}
  else if(state.stage==="verified"){label="RECOVERY VERIFIED";tone="passed";}
  else if(state.execution){label="ACTION COMPLETED · VERIFY NEXT";tone="passed";}
  else if(state.stage==="stopped"){label="INVESTIGATION STOPPED";tone="blocked";}
  else if(state.execution_policy_phase==="preview"&&!evaluation.allowed){label="PRECHECK BLOCKED · NOT EXECUTED";tone="blocked";}
  else if(state.stage==="approved"){label="APPROVED · EXECUTOR RECHECKS NEXT";tone="passed";}
  else if(state.stage==="planned"){label="AWAITING HUMAN APPROVAL";}
  else if(state.diagnosis?.status==="supported_hypothesis"){label="EVIDENCE CHECK PASSED · NO PLAN YET";tone="passed";}
  const input=packet?`<dl class="contract"><dt>Observation records</dt><dd>${packet.observations.length}</dd><dt>Input through</dt><dd>${atInvestigation?clock(atInvestigation.scenario_s):"—"}</dd><dt>Latest memory</dt><dd>${atInvestigation?.payload.memory_observed?`${atInvestigation.payload.memory_mb} MB`:"Missing"}</dd><dt>DB in model input</dt><dd>${atInvestigation?.payload.db_pct??"—"}%</dd><dt>Selected runbooks</dt><dd>${packet.runbooks.map(b=>esc(b.id)).join("<br>")}</dd></dl><details class="payload-view"><summary>Inspect evidence packet</summary><pre>${esc(JSON.stringify(packet,null,2))}</pre></details>`:`<p class="muted">Run the investigation to assemble selected observations and runbooks.</p>`;
  const output=report?`<dl class="contract"><dt>Actual response</dt><dd>${report.model_invoked?"Received":"Not received"}</dd><dt>Format + references</dt><dd>${report.validated?"Accepted":"Rejected / unavailable"}</dd><dt>Proposed action</dt><dd>${esc(analysis?.proposed_action||"None accepted")}</dd></dl>${analysis?`<p class="model-summary">${esc(analysis.summary)}</p><p class="small">Evidence ${analysis.evidence.map(n=>`#${n}`).join(", ")}</p>`:""}${report.error?`<p class="callout">${esc(report.error)}</p>`:""}${report.response_text?`<details class="payload-view"><summary>Inspect actual model output</summary><pre>${esc(report.response_text)}</pre></details>`:""}`:`<p class="muted">${state.ai_required?"No model response yet.":"Explicit rules baseline: no model call or generated response."}</p>`;
  const ruleChecks=rule?[{name:"Independent scenario evidence rule",passed:rule.status==="supported_hypothesis"}]:[];
  const failed=(evaluation?.checks||[]).filter(c=>!c.passed);
  const policyView=evaluation?`<p class="small">${state.execution_policy?(state.execution_policy_phase==="preview"?"Current-condition preview; execution not attempted yet.":"Checks recorded at execution attempt."):"Plan admission; execution checks run again later."}</p>${checks(failed.length?failed:evaluation.checks)}`:rule?checks(ruleChecks):`<p class="muted">No investigation decision yet.</p>`;
  return `<div class="decision-grid"><article class="decision-card"><h3>1. Input</h3>${input}</article><article class="decision-card"><h3>2. Model output</h3>${output}<p class="small">A generated explanation is not execution permission.</p></article><article class="decision-card"><h3>3. Independent decision</h3><p class="decision-status ${tone}" role="status">${label}</p><div class="evidence-row"><span>Recovery mutations</span><strong id="mutation-count">${mutations}</strong></div><div class="evidence-row"><span>Current DB pressure</span><strong>${current.db_pct}%</strong></div>${rule?`<p class="small rule-summary">At investigation: ${esc(rule.summary)}</p>`:""}${policyView}${state.condition_change?`<p class="callout">A later scenario observation changed DB pressure from ${state.condition_change.before_db_pct}% to ${state.condition_change.after_db_pct}%. No new model call; the plan and approval are unchanged.</p>`:""}</article></div>`;
}
function journal(){
  return `<div class="journal-list">${[...state.journal].reverse().map(e=>`<details class="journal-event"><summary><span>#${e.seq}</span><span>${clock(e.scenario_s)}</span><strong>${esc(e.kind)}</strong></summary><pre>${esc(JSON.stringify(e.payload,null,2))}</pre></details>`).join("")}</div>`;
}
function renderControls(){
  const [label,path]=buttons[state.stage]; $("next").textContent=label;$("next").disabled=!path;
  $("next").onclick=()=>command(path);
  const auxiliary=$("auxiliary");auxiliary.hidden=false;
  if(state.stage==="planned"){auxiliary.textContent="Why not scale out?";auxiliary.onclick=()=>{tab="action";command("unsafe-scale");};}
  else if(state.stage==="verified" && !state.duplicate){auxiliary.textContent="Retry the same action";auxiliary.onclick=()=>{tab="investigation";command("execute");};}
  else if(state.stage==="verified"){auxiliary.textContent="Replay recorded history";auxiliary.onclick=()=>{tab="investigation";command("replay");};}
  else auxiliary.hidden=true;
  const challenge=$("challenge");
  challenge.hidden=state.stage!=="approved"||!!state.condition_change;
  challenge.disabled=document.body.classList.contains("busy");
  challenge.onclick=()=>command("challenge-db");
}
function render(){
  const m=state.metrics.at(-1);
  $("headline").textContent=state.headline;$("explanation").textContent=state.explanation;$("phase").textContent=state.stage.toUpperCase();
  $("clock").textContent=clock(state.scenario_s);$("queue-node").textContent=`${m.queue_age_s} s oldest work`;
  $("revision-node").textContent=`${state.revision.replace("worker:","")} · ${state.replicas} replicas`;
  $("db-node").textContent=`${m.db_pct}% utilization`;
  $("worker-node").classList.toggle("fault",state.revision==="worker:v2");
  $("queue-value").innerHTML=`${m.queue_age_s} <small>s</small>`;$("queue-value").className="metric-value "+(m.queue_age_s>30?"bad":"good");
  $("memory-value").innerHTML=m.memory_mb===null?`Missing <small>evidence</small>`:`${m.memory_mb} <small>MB</small>`;
  $("memory-value").className="metric-value "+(!m.memory_observed||m.memory_mb>400?"bad":"good");
  $("latency-value").innerHTML=`${m.p95_ms} <small>ms</small>`;$("latency-value").className="metric-value "+(m.p95_ms>300?"bad":"good");
  chart("queue-chart","queue_age_s",60,30);chart("memory-chart","memory_mb",520,512);chart("latency-chart","p95_ms",1100,300);
  const sequence=["baseline","incident","evidence","diagnosed","planned","approved","executed","verified"];
  let phase=sequence.indexOf(state.stage);if(state.stage==="stopped")phase=state.verification?7:state.execution_blocked?6:3;
  const steps=[["Observe",1],["Preserve",2],["Diagnose",3],["Authorize",5],["Execute",6],["Verify",7]];
  $("stages").innerHTML=steps.map(([name,limit],i)=>`<div class="stage ${phase>limit?"done":phase===limit||(phase===0&&i===0)||(phase===4&&i===3)?"active":""}"><span>0${i+1}</span>${name}</div>`).join("");
  document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-selected",b.dataset.tab===tab));
  $("run-label").textContent=`RUN ${state.run_id} · JOURNAL ${state.integrity.valid?"VERIFIED":"MISMATCH"}`;
  $("detail").innerHTML=tab==="investigation"?investigation():tab==="ai"?aiInvestigation():tab==="decision"?inputDecision():tab==="action"?action():journal();
  renderControls();
}
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>{tab=b.dataset.tab;render();}));
$("new-run").onclick=()=>command("new",{scenario:$("scenario").value});
fetch("/api/state").then(r=>r.json()).then(s=>{state=s;render();}).catch(e=>{$("error").textContent=e.message;$("error").hidden=false;});
