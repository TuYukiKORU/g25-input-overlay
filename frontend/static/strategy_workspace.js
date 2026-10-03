(() => {
  'use strict';
  const $ = id => document.getElementById(id), query = new URLSearchParams(location.search);
  const state = {sessions: [], context: null, result: null, goal: ['race','compare','qualifying'].includes(query.get('goal')) ? query.get('goal') : 'race',
    scenario: 'lift_and_deploy', section: null, busy: false, dirty: false, version: 0};
  const actionNames = {none:'No extra operation',boost:'Boost',overtake:'Overtake',lift_10:'Lift 10%',lift_20:'Lift 20%',lift_30:'Lift 30%'};
  const kinds = {braking:'Braking',lift:'Lift',acceleration:'Acceleration',flat_out:'Full throttle'};
  const colors = {none:'#42525b',boost:'#f6d65c',overtake:'#35a7ff',lift_10:'#ffb659',lift_20:'#ffb659',lift_30:'#ffb659'};
  const finite = value => value !== null && value !== undefined && Number.isFinite(Number(value));
  const formatTime = ms => finite(ms) ? `${Math.floor(ms/60000)}:${((ms%60000)/1000).toFixed(3).padStart(6,'0')}` : '—';
  const percent = value => finite(value) ? `${Number(value).toFixed(1)}%` : '—';
  function node(tag, text, className) {const n = document.createElement(tag);if(text != null)n.textContent = text;if(className)n.className=className;return n;}
  function options(select, values, value, label) {select.replaceChildren(...values.map(item=>{const option=node('option',label(item));option.value=String(value(item));return option;}));}
  async function json(url, options) {const response=await fetch(url,{cache:'no-store',...options});const data=await response.json();if(!response.ok)throw new Error(data.error || `Request failed (${response.status})`);return data;}
  function session() {return state.sessions.find(s=>s.id===$('sessionSelect').value);}
  function track() {return session()?.tracks.find(t=>String(t.trackId)===$('trackSelect').value);}
  function contextParams() {return new URLSearchParams({session:$('sessionSelect').value,track_id:$('trackSelect').value,selected_lap_id:$('lapSelect').value});}
  function remember() {
    SessionContext.write($('sessionSelect').value,$('trackSelect').value);
    const params=contextParams();params.set('goal',state.goal);history.replaceState(null,'',`/strategy?${params}`);
    $('sessionReportLink').href=`/session-analysis?${contextParams()}`;
    const corners=contextParams();corners.set('edit','1');$('editCornersLink').href=`/map-corners?${corners}`;
    document.querySelectorAll('[data-context-link]').forEach(a=>a.href=a.dataset.contextLink==='report'?$('sessionReportLink').href:$('editCornersLink').href);
  }
  function showError(message) {$('errorMessage').textContent=message || '';$('errorMessage').hidden=!message;}
  function updateBuildButton() {$('buildPlan').disabled=state.busy || !state.context?.readiness?.ready;}
  function setBusy(value) {
    state.busy=value;document.querySelectorAll('.context-controls select,.plan-controls input,.plan-controls select,.goal-tabs button').forEach(el=>el.disabled=value);
    $('jobProgress').hidden=!value;updateBuildButton();
  }
  function pending() {
    state.dirty=true;
    $('calculationState').classList.add('dirty');
    $('calculationState').textContent=state.result?'Inputs changed — build the plan to update these results.':'Ready to build from the selected inputs.';
    if(state.result)$('resultStatus').textContent='Needs recalculation';
  }
  function setGoal(goal) {
    state.goal=goal;document.querySelectorAll('[data-goal]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.goal===goal)));
    document.querySelectorAll('.race-control').forEach(el=>el.hidden=goal!=='race');
    $('deploymentControl').hidden=goal==='qualifying';$('lineControl').hidden=goal!=='qualifying';
    $('startLabel').textContent=goal==='qualifying'?'Battery before run-up (%)':'Starting battery (%)';
    pending();if(session() && track())remember();
  }
  function renderReadiness() {
    const context=state.context, ready=context?.readiness;
    $('readiness').replaceChildren();
    if(!ready)return;
    const edition=node('span',ready.edition?`Detected edition: F1 ${String(ready.edition).slice(2)}`:'Edition unknown');
    edition.className=ready.edition===2026?'':'unavailable';$('readiness').append(edition);
    for(const [label,available] of [['Battery data',ready.energy?.available],['Map positions',ready.geometry?.available]]){
      const item=node('span',`${label}: ${available?'available':'unavailable'}`,available?'':'unavailable');$('readiness').append(item);
    }
    $('readiness').append(node('span',`${context.comparable_lap_count} comparable source laps`));
    $('calculationState').textContent=ready.ready?'Ready to build from the selected inputs.':ready.reason || 'More comparable telemetry is required.';
    $('calculationState').classList.toggle('dirty',!ready.ready);updateBuildButton();
  }
  async function loadContext(useRequested=false) {
    const version=++state.version, current=track();state.context=null;state.result=null;state.section=null;state.dirty=false;
    $('readiness').replaceChildren();
    $('planResults').hidden=true;$('emptyState').hidden=false;showError('');updateBuildButton();
    $('calculationState').textContent='Checking recorded telemetry and comparison conditions…';
    if(!current){$('lapSelect').replaceChildren();$('readiness').replaceChildren();$('calculationState').textContent='No saved laps are available.';return;}
    const wanted=useRequested?query.get('selected_lap_id'):$('lapSelect').value;
    options($('lapSelect'),current.laps,l=>l.id,l=>`Lap ${l.lapNumber} · ${formatTime(l.lapTimeMs)} · ${l.validLap?'valid':'invalid'}`);
    const existing=current.laps.find(l=>l.id===wanted);
    const selected=existing || current.laps.filter(l=>l.validLap && !l.pitLaneUsed).sort((a,b)=>a.lapTimeMs-b.lapTimeMs)[0] || current.laps[0];
    if(!selected)return;$('lapSelect').value=selected.id;
    try {
      const params=new URLSearchParams({track_id:current.trackId,selected_lap_id:selected.id});
      const context=await json(`/api/sessions/${encodeURIComponent(session().id)}/strategy-context?${params}`);
      if(version!==state.version)return;state.context=context;
      const lap=context.laps.find(l=>l.id===selected.id);
      if(finite(lap?.end_soc))$('startSoc').value=Number(lap.end_soc).toFixed(1);
      renderReadiness();remember();
    } catch(error) {if(version===state.version){showError(error.message);$('calculationState').textContent='Could not check this recording.';}}
  }
  function chooseTrack(requested) {
    const current=session();options($('trackSelect'),current?.tracks||[],t=>t.trackId,t=>t.trackName);
    const chosen=SessionContext.chooseTrack(current,requested);if(chosen)$('trackSelect').value=String(chosen.trackId);
  }
  function activePlan() {
    const result=state.result;if(!result)return null;
    if(result.goal==='compare')return result.plan.scenarios.find(s=>s.id===state.scenario && s.analyzable) || result.plan.scenarios.find(s=>s.analyzable);
    return result.plan;
  }
  function nextLap() {const p=activePlan();return p?.current_lap_recommendation || p?.trajectory?.[0] || p;}
  function activeAllocations() {return nextLap()?.allocations || [];}
  function renderScenarios() {
    const result=state.result;$('scenarioChoices').hidden=result.goal!=='compare';$('scenarioChoices').replaceChildren();
    if(result.goal!=='compare')return;
    const active=activePlan();state.scenario=active?.id;
    for(const row of result.plan.scenarios){
      const button=node('button',null);button.type='button';button.disabled=!row.analyzable;button.setAttribute('aria-pressed',String(row.id===active?.id));
      button.append(node('span',row.label),node('b',formatTime(row.predicted_lap_time_ms)),node('small',`Finish battery: ${percent(row.predicted_finish_soc)}`));
      button.append(node('small',row.analyzable?(row.comparable?`Within ±${result.plan.finish_soc_tolerance}% of finish target`:`Different reserve: ${Number(row.finish_soc_error).toFixed(2)} percentage points`):row.reason,
                         row.comparable?'':'not-comparable'));
      if(row.comparable && row.id!=='no_deployment')button.append(node('small',`Estimated gain: ${(row.net_gain_vs_no_deployment_ms/1000).toFixed(3)} s`));
      button.addEventListener('click',()=>{state.scenario=row.id;state.section=null;renderResults();});$('scenarioChoices').append(button);
    }
  }
  function renderForecast() {
    const result=state.result,p=activePlan(),rows=p?.trajectory || [];$('forecast').replaceChildren();
    $('forecastTitle').textContent=result.goal==='compare'?'Single-lap comparison':result.goal==='qualifying'?'Qualifying battery plan':'Battery over the next laps';
    rows.forEach((row,index)=>{const card=node('article');card.append(node('span',index===0?'Next lap':`Lap +${index+1}`),node('b',percent(row.soc_end)),node('small',`${formatTime(row.predicted_lap_time_ms)} · estimated`));$('forecast').append(card);});
    if(result.goal==='qualifying'){
      $('forecastNotice').textContent=`Before run-up ${percent(p.battery_before_runup_soc)} → timing line ${percent(p.start_line_soc)}. Required at line: ${percent(p.pre_start_runup.minimum_start_line_soc)}.`;
    }else if(result.goal==='compare'){
      $('forecastNotice').textContent=`Common finish target ${percent(result.plan.common_finish_soc)}. Only alternatives within ±${result.plan.finish_soc_tolerance}% are ranked.`;
    }else $('forecastNotice').textContent=`Use the next-lap plan; rebuild after measuring battery. Horizon finish target: ${percent(p.target_finish_soc)}.`;
    $('curveNotice').textContent=`Minimum battery on this lap: ${percent(nextLap()?.minimum_soc)}. Reserve setting: ${percent(result.settings.minimum_soc)}.`;
  }
  function renderSections() {
    const sections=state.result.reference_sections,allocations=activeAllocations();$('actionStrip').replaceChildren();$('allocationRows').replaceChildren();
    sections.forEach(section=>{
      const allocation=allocations.find(a=>a.section_number===section.number),action=allocation?.action||'none';
      const button=node('button');button.type='button';button.dataset.action=action;button.dataset.section=String(section.number);
      button.style.flexGrow=Math.max(1,section.end_distance-section.start_distance);button.setAttribute('aria-label',`Section ${section.number}: ${actionNames[action]}, ${Math.round(section.start_distance)}–${Math.round(section.end_distance)} m`);
      button.setAttribute('aria-pressed',String(state.section===section.number));button.addEventListener('click',()=>{state.section=section.number;renderSections();drawMap();});$('actionStrip').append(button);
      const row=node('tr');[section.number,`${Math.round(section.start_distance)}–${Math.round(section.end_distance)} m`,actionNames[action],allocation?`${Math.round((allocation.applied_fraction??1)*100)}%`:'—',allocation?.evidence || 'baseline'].forEach(value=>row.append(node('td',value)));$('allocationRows').append(row);
    });
    const section=sections.find(s=>s.number===state.section),allocation=allocations.find(a=>a.section_number===state.section);
    $('sectionDetail').textContent=section?`Section ${section.number} · ${Math.round(section.start_distance)}–${Math.round(section.end_distance)} m · ${actionNames[allocation?.action||'none']} · ${allocation?.evidence||'baseline'}${allocation?` · ${Math.round((allocation.applied_fraction??1)*100)}% modeled coverage`:''}`:'Select a section to inspect its action and evidence.';
  }
  function renderEvidence() {
    const summary=state.result.model_summary,source=summary.source,entries=state.result.evidence.action_entries;
    $('evidenceSummary').textContent=`${source.eligible_laps} source laps · ${source.sessions} sessions · ${entries.observed||0} observed / ${(entries.inferred||0)+(entries.inferred_baseline||0)} inferred section/action entries. ${state.result.evidence.rejected_action_entries} contradictory actions excluded.`;
    $('conditionNotice').textContent=`Unknown comparison fields: ${summary.selection.unknown_conditions.join(', ') || 'none'}. Known mismatches are excluded; missing fields limit confidence. Pace window: ${source.pace_window_percent}%.`;
    $('excludedNotice').textContent='Excluded laps: '+Object.entries(summary.selection.excluded).filter(([,n])=>n).map(([reason,n])=>`${n} ${reason.replaceAll('_',' ')}`).join(' · ');
    $('assumptionList').replaceChildren(...state.result.assumptions.map(text=>node('li',text)));
    $('sourceRows').replaceChildren(...source.laps.map(lap=>{const row=node('tr');[`${lap.id.split('/')[0]} · Lap ${lap.lap_number}`,formatTime(lap.lap_time_ms),lap.conditions.compound||'Unknown',finite(lap.conditions.fuel)?`${Number(lap.conditions.fuel).toFixed(1)} kg`:'Unknown'].forEach(value=>row.append(node('td',value)));return row;}));
    $('referenceRows').replaceChildren(...state.result.reference_sections.map(s=>{const row=node('tr');[s.number,`${Math.round(s.start_distance)}–${Math.round(s.end_distance)} m`,kinds[s.kind]||s.kind,`${Number(s.average_speed).toFixed(0)} km/h`].forEach(value=>row.append(node('td',value)));return row;}));
  }
  function canvas(id) {const el=$(id),rect=el.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,2);el.width=Math.round(rect.width*ratio);el.height=Math.round(rect.height*ratio);const ctx=el.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.font='13px Inter,system-ui';return {ctx,w:rect.width,h:rect.height};}
  function drawMap() {
    const result=state.result;if(!result || $('planResults').hidden)return;
    const geometry=result.readiness.geometry;$('planMap').hidden=!geometry.available;$('mapNotice').hidden=geometry.available;
    $('mapNotice').textContent=geometry.reason || 'Track positions are unavailable. Use the distance strip and battery chart.';
    if(!geometry.available)return;
    const points=result.model_summary.track_points.filter(p=>finite(p.x)&&finite(p.z));if(points.length<2)return;
    const {ctx,w,h}=canvas('planMap'),pad=28,xs=points.map(p=>p.x),zs=points.map(p=>p.z),minX=Math.min(...xs),maxX=Math.max(...xs),minZ=Math.min(...zs),maxZ=Math.max(...zs);
    const scale=Math.min((w-pad*2)/Math.max(1,maxX-minX),(h-pad*2)/Math.max(1,maxZ-minZ));
    const project=p=>({x:(w-(maxX-minX)*scale)/2+(p.x-minX)*scale,y:(h-(maxZ-minZ)*scale)/2+(maxZ-p.z)*scale});
    const allocations=activeAllocations();ctx.lineCap='round';ctx.lineJoin='round';
    for(let i=1;i<points.length;i++){const a=project(points[i-1]),b=project(points[i]),allocation=allocations.find(r=>points[i].s>=r.start_distance && points[i].s<=r.end_distance);ctx.strokeStyle=colors[allocation?.action||'none'];ctx.lineWidth=6;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
    const selected=result.reference_sections.find(s=>s.number===state.section);if(selected){const p=points.reduce((best,p)=>Math.abs(p.s-(selected.start_distance+selected.end_distance)/2)<Math.abs(best.s-(selected.start_distance+selected.end_distance)/2)?p:best,points[0]),xy=project(p);ctx.strokeStyle='#edf3f4';ctx.lineWidth=2;ctx.beginPath();ctx.arc(xy.x,xy.y,9,0,Math.PI*2);ctx.stroke();}
    const start=project(points[0]);ctx.fillStyle='#6fe7bf';ctx.beginPath();ctx.arc(start.x,start.y,4,0,Math.PI*2);ctx.fill();
  }
  function drawSoc() {
    if(!state.result || $('planResults').hidden)return;const trace=nextLap()?.soc_trace || [],{ctx,w,h}=canvas('socChart');if(trace.length<2)return;
    const left=41,right=15,top=24,bottom=37,length=state.result.model_summary.track_length_m;
    const x=s=>left+s/length*(w-left-right),y=soc=>h-bottom-soc/100*(h-top-bottom);
    ctx.fillStyle='#a4b3ba';ctx.textAlign='right';[0,25,50,75,100].forEach(v=>{ctx.strokeStyle='#29383e';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,y(v));ctx.lineTo(w-right,y(v));ctx.stroke();ctx.fillText(String(v),left-8,y(v)+4);});
    const ticks=w<400?[0,length]:[0,length/2,length];ticks.forEach((s,i)=>{ctx.textAlign=i===0?'left':i===ticks.length-1?'right':'center';ctx.fillText(`${(s/1000).toFixed(1)} km`,x(s),h-12);});ctx.textAlign='left';ctx.fillText('Battery (%)',left,13);
    ctx.strokeStyle='#edc17a';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(left,y(state.result.settings.minimum_soc));ctx.lineTo(w-right,y(state.result.settings.minimum_soc));ctx.stroke();ctx.setLineDash([]);
    ctx.strokeStyle='#6fe7bf';ctx.lineWidth=2;ctx.beginPath();trace.forEach((p,i)=>i?ctx.lineTo(x(p.distance),y(p.soc)):ctx.moveTo(x(p.distance),y(p.soc)));ctx.stroke();
  }
  function renderResults() {
    const result=state.result;if(!result)return;
    if(!result.analyzable){$('planResults').hidden=true;$('emptyState').hidden=false;showError(result.reason || result.plan.reason || 'No feasible plan for these inputs.');return;}
    $('planResults').hidden=false;$('emptyState').hidden=true;
    $('resultTitle').textContent=result.goal==='qualifying'?'Qualifying energy plan':result.goal==='compare'?'Compare energy scenarios':'Next-lap energy plan';
    $('resultContext').textContent=`${track()?.trackName || 'Track'} · F1 26 · ${result.settings.start_soc??result.plan.start_soc}% starting battery · ${result.settings.minimum_soc}% reserve · ${result.goal==='qualifying'?'Overtake':result.settings.deployment_mode} · built from selected reference lap`;
    $('resultStatus').textContent=state.dirty?'Needs recalculation':'Estimated plan';
    renderScenarios();renderForecast();renderSections();renderEvidence();drawMap();drawSoc();
    if(query.get('panel')==='reference')$('referencePanel').open=true;
  }
  async function build(event) {
    event.preventDefault();if(state.busy || !state.context?.readiness.ready || !$('planForm').reportValidity())return;
    const version=state.version,target=session().id;
    const settings={track_id:track().trackId,selected_lap_id:$('lapSelect').value,goal:state.goal,deployment_mode:$('deploymentMode').value,
      start_soc:Number($('startSoc').value),minimum_soc:Number($('reserveSoc').value),minimum_start_line_soc:Number($('lineSoc').value),horizon:Number($('horizon').value),
      remaining_laps:$('remainingLaps').value?Number($('remainingLaps').value):null};
    showError('');setBusy(true);$('jobProgress').value=0;$('planResults').hidden=true;$('emptyState').hidden=true;
    $('calculationState').classList.remove('dirty');$('calculationState').textContent='Queued for calculation…';
    try {
      let status=await json(`/api/sessions/${encodeURIComponent(target)}/analysis/workspace`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});
      const params=new URLSearchParams({track_id:settings.track_id,analysis_id:status.analysis_id}),base=`/api/sessions/${encodeURIComponent(target)}/analysis/workspace`;
      const deadline=Date.now()+300000;
      while(status.state!=='completed'){
        if(status.state==='failed')throw new Error(status.error || 'Plan calculation failed.');
        if(Date.now()>deadline)throw new Error('Calculation is still running. Build again to reconnect to this job.');
        $('jobProgress').value=status.progress || 0;$('calculationState').textContent=`Calculating · ${status.progress || 0}% · ${status.current || ''}`;
        await new Promise(resolve=>setTimeout(resolve,900));status=await json(`${base}/status?${params}`);
      }
      const result=await json(`${base}/result?${params}`);if(version!==state.version)return;
      state.result=result;state.dirty=Boolean(result.stale);state.section=null;
      $('calculationState').textContent=`${status.cached?'Cached plan loaded':'Plan built'} · ${new Date(result.generated_at).toLocaleTimeString()}${result.stale?' · sources changed; rebuild required':''}`;
      renderResults();
    } catch(error){showError(error.message);$('emptyState').hidden=false;$('calculationState').textContent='Plan unavailable for these inputs.';}
    finally{setBusy(false);}
  }
  $('planForm').addEventListener('submit',build);
  $('planForm').querySelectorAll('input,select').forEach(el=>el.addEventListener('input',pending));
  document.querySelectorAll('[data-goal]').forEach(button=>button.addEventListener('click',()=>setGoal(button.dataset.goal)));
  $('sessionSelect').addEventListener('change',()=>{chooseTrack();loadContext();});$('trackSelect').addEventListener('change',()=>loadContext());$('lapSelect').addEventListener('change',()=>loadContext());
  $('inspectEvidence').addEventListener('click',()=>{$('evidencePanel').open=true;$('evidencePanel').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});});
  new ResizeObserver(()=>{drawMap();drawSoc();}).observe($('planResults'));
  async function init() {
    setGoal(state.goal);state.sessions=await json('/api/sessions');
    options($('sessionSelect'),state.sessions,s=>s.id,SessionContext.sessionLabel);
    let chosen=SessionContext.chooseSession(state.sessions,query.get('session')||query.get('session_id'));
    if(query.has('track_id') && !chosen?.tracks.some(t=>String(t.trackId)===query.get('track_id')))chosen=state.sessions.find(s=>s.tracks.some(t=>String(t.trackId)===query.get('track_id'))) || chosen;
    if(chosen)$('sessionSelect').value=chosen.id;chooseTrack(query.get('track_id'));await loadContext(true);
  }
  init().catch(error=>{showError(error.message);$('calculationState').textContent='Could not load saved sessions.';});
})();
