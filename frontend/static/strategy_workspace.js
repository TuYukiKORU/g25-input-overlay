(() => {
  'use strict';
  const $ = id => document.getElementById(id), query = new URLSearchParams(location.search);
  const state = {sessions: [], context: null, result: null, goal: ['race','compare','qualifying','practice'].includes(query.get('goal')) ? query.get('goal') : 'race',
    scenario: 'lift_and_deploy', section: null, busy: false, dirty: false, version: 0};
  const actionNames = {none:'No extra operation',boost:'Boost',overtake:'Overtake',lift_10:'Lift 10%',lift_20:'Lift 20%',lift_30:'Lift 30%'};
  const kinds = {braking:'Braking',lift:'Lift',acceleration:'Acceleration',flat_out:'Full throttle'};
  const colors = {none:'#42525b',control:'#6fe7bf',boost:'#f6d65c',overtake:'#35a7ff',lift_10:'#ffb659',lift_20:'#ffb659',lift_30:'#ffb659'};
  const practiceReasons = {missing_pair:'Record a control before testing this mode',missing_mode:'No recorded use of this mode',missing_baseline:'Missing a no-extra-ERS control',few_repeats:'Too few repeated comparisons',unmatched_entry:'Match starting charge and entry speed',variable_energy:'Battery change varies between repeats'};
  const finite = value => value !== null && value !== undefined && Number.isFinite(Number(value));
  const formatTime = ms => finite(ms) ? `${Math.floor(ms/60000)}:${((ms%60000)/1000).toFixed(3).padStart(6,'0')}` : '—';
  const percent = value => finite(value) ? `${Number(value).toFixed(1)}%` : '—';
  function node(tag, text, className) {const n = document.createElement(tag);if(text != null)n.textContent = text;if(className)n.className=className;return n;}
  function options(select, values, value, label) {select.replaceChildren(...values.map(item=>{const option=node('option',label(item));option.value=String(value(item));return option;}));}
  async function json(url, options) {const response=await fetch(url,{cache:'no-store',...options});const data=await response.json();if(!response.ok)throw new Error(data.error || `Request failed (${response.status})`);return data;}
  function session() {return state.sessions.find(s=>s.id===$('sessionSelect').value);}
  function track() {return session()?.tracks.find(t=>String(t.trackId)===$('trackSelect').value);}
  function recordedActivity() {return SessionContext.activityLabel(track()?.laps.find(l=>l.id===$('lapSelect').value)||session());}
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
    document.querySelectorAll('.plan-controls input,.plan-controls select').forEach(el=>el.disabled=value||Boolean(el.closest('[hidden]')));
    $('jobProgress').hidden=!value;updateBuildButton();
  }
  function pending() {
    state.dirty=true;
    $('calculationState').classList.add('dirty');
    $('calculationState').textContent=state.result?'Inputs changed — build the plan to update these results.':'Ready to build from the selected inputs.';
    if(state.result)$('resultStatus').textContent='Needs recalculation';
  }
  function setGoal(goal) {
    const changedPool=(state.goal==='practice')!==(goal==='practice');
    state.goal=goal;document.querySelectorAll('[data-goal]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.goal===goal)));
    document.querySelectorAll('.race-control').forEach(el=>el.hidden=goal!=='race');
    $('deploymentControl').hidden=goal==='qualifying';$('qualifyingBoundary').hidden=goal!=='qualifying';
    $('boostLegend').hidden=goal==='qualifying';
    $('raceStartControl').hidden=goal!=='race';$('startControl').hidden=goal!=='compare';$('reserveControl').hidden=goal==='qualifying'||goal==='practice';
    $('buildPlan').textContent=goal==='practice'?'Build practice map':'Build plan';
    $('emptyTitle').textContent=goal==='practice'?'Where to collect the next comparison':'Plan the next lap';
    $('emptyDescription').textContent=goal==='practice'?'Choose a reference lap and mode, then build a map of missing ERS comparisons.':'Choose a goal and build a plan. Battery curves, track actions and forecasts will use one shared calculation.';
    $('emptyScope').textContent=goal==='practice'?'Test one section per lap. Repeat the same markers with and without ERS, then record and rebuild this map.':'Race energy covers a 3–5 lap horizon. Pit stops, traffic and weather changes are outside this model.';
    setBusy(state.busy);
    pending();if(session() && track()){remember();if(changedPool)loadContext();}
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
    $('readiness').append(node('span',`Recorded session: ${recordedActivity()}`));
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
    options($('lapSelect'),current.laps,l=>l.id,l=>`Lap ${l.lapNumber} · ${formatTime(l.lapTimeMs)} · ${l.validLap?'valid':'invalid'}${window.SessionContext.rewindLabel(l)}`);
    const existing=current.laps.find(l=>l.id===wanted);
    const selected=existing || current.laps.filter(l=>l.validLap && !l.pitLaneUsed).sort((a,b)=>a.lapTimeMs-b.lapTimeMs)[0] || current.laps[0];
    if(!selected)return;$('lapSelect').value=selected.id;
    try {
      const params=new URLSearchParams({track_id:current.trackId,selected_lap_id:selected.id,goal:state.goal});
      const context=await json(`/api/sessions/${encodeURIComponent(session().id)}/strategy-context?${params}`);
      if(version!==state.version)return;state.context=context;
      const lap=context.laps.find(l=>l.id===selected.id);
      if(finite(lap?.end_soc)){
        $('startSoc').value=Number(lap.end_soc).toFixed(1);
        $('raceStartSoc').value=String(Math.max(0,Math.min(100,Math.round(Number(lap.end_soc)/10)*10)));
      }
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
  function activeAllocations() {return state.result?.goal==='practice'?state.result.plan.targets.map(t=>({...t,action:t.action==='none'?'control':t.action})):nextLap()?.allocations || [];}
  function practiceInstruction(target) {
    const distance=`${Math.round(target.start_distance)}–${Math.round(target.end_distance)} m`;
    const action=['none','control'].includes(target.action)?'Control: no extra ERS':`Test ${actionNames[target.action]}`;
    return `${action} · ${distance}. ${practiceReasons[target.reason]}.${finite(target.suggested_entry_soc)?` Match entry battery near ${percent(target.suggested_entry_soc)}.`:''} Keep the other sections unchanged; stop before braking. Skip if grip, mode availability or battery reserve is insufficient.`;
  }
  function renderPractice() {
    const practice=state.result.goal==='practice';
    $('practicePanel').hidden=!practice;$('energyForecastPanel').hidden=practice;
    $('energyLegend').hidden=practice;$('practiceLegend').hidden=!practice;$('plannedSections').hidden=practice;
    $('mapTitle').textContent=practice?'ERS practice map':'Next-lap energy plan';
    if(!practice)return;
    const plan=state.result.plan;$('practiceNotice').textContent=plan.message;
    $('practiceTargets').replaceChildren(...plan.targets.map(target=>{
      const button=node('button');button.type='button';button.setAttribute('aria-pressed',String(state.section===target.section_number));
      button.append(node('b',`${target.rank}. Section ${target.section_number} · ${target.action==='none'?'Control: no extra ERS':`Test ${actionNames[target.action]}`}`),
        node('span',practiceReasons[target.reason]),
        node('small',`${target.baseline_laps} control laps · ${target.deployment_laps} ${actionNames[plan.deployment_mode]} laps · ${target.matched_entry_laps} matched entries`),
        node('small',`Observed battery variation: ${finite(target.soc_delta_mad)?`${Number(target.soc_delta_mad).toFixed(2)} percentage points`:'—'}`));
      button.addEventListener('click',()=>{state.section=target.section_number;renderPractice();renderSections();drawMap();});return button;
    }));
    const target=plan.targets.find(t=>t.section_number===state.section);
    $('practiceDetail').textContent=target?practiceInstruction(target):'Select a numbered target to inspect its next test.';
  }
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
    if(state.result.goal==='practice')return;
    const result=state.result,p=activePlan(),rows=p?.trajectory || [];$('forecast').replaceChildren();
    $('forecastTitle').textContent=result.goal==='compare'?'Single-lap comparison':result.goal==='qualifying'?'Qualifying battery plan':'Battery over the next laps';
    rows.forEach((row,index)=>{const card=node('article');card.append(node('span',index===0?'Next lap':`Lap +${index+1}`),node('b',percent(row.soc_end)),node('small',`${formatTime(row.predicted_lap_time_ms)} · estimated`));$('forecast').append(card);});
    if(result.goal==='qualifying'){
      $('forecastNotice').textContent=`Fixed start: 100%. Finish target: 0%. Predicted finish: ${percent(p.predicted_finish_soc)}.${p.finish_target_reached?'':' Available deployment estimates cannot reach the finish target; this is the closest feasible plan.'}${p.energy_estimation?' '+p.energy_estimation:''}`;
    }else if(result.goal==='compare'){
      $('forecastNotice').textContent=`Common finish target ${percent(result.plan.common_finish_soc)}. Only alternatives within ±${result.plan.finish_soc_tolerance}% are ranked.`;
    }else $('forecastNotice').textContent=`Use the next-lap plan; rebuild after measuring battery. Horizon finish target: ${percent(p.target_finish_soc)}.`;
    $('curveNotice').textContent=`Minimum battery on this lap: ${percent(nextLap()?.minimum_soc)}. Reserve setting: ${percent(result.settings.minimum_soc)}.`;
  }
  function renderSections() {
    const practice=state.result.goal==='practice';
    const sections=state.result.reference_sections,allocations=activeAllocations();$('actionStrip').replaceChildren();$('allocationRows').replaceChildren();
    sections.forEach(section=>{
      const allocation=allocations.find(a=>a.section_number===section.number),action=allocation?.action||'none';
      const button=node('button');button.type='button';button.dataset.action=action;button.dataset.section=String(section.number);
      button.style.flexGrow=Math.max(1,section.end_distance-section.start_distance);button.setAttribute('aria-label',`Section ${section.number}: ${action==='control'?'Control: no extra ERS':actionNames[action]}, ${Math.round(section.start_distance)}–${Math.round(section.end_distance)} m`);
      button.setAttribute('aria-pressed',String(state.section===section.number));button.addEventListener('click',()=>{state.section=section.number;renderSections();renderPractice();drawMap();});$('actionStrip').append(button);
      const row=node('tr');[section.number,`${Math.round(section.start_distance)}–${Math.round(section.end_distance)} m`,actionNames[action],allocation?`${Math.round((allocation.applied_fraction??1)*100)}%`:'—',allocation?.evidence || 'baseline'].forEach(value=>row.append(node('td',value)));$('allocationRows').append(row);
    });
    const section=sections.find(s=>s.number===state.section),allocation=allocations.find(a=>a.section_number===state.section);
    $('sectionDetail').textContent=section?`Section ${section.number} · ${Math.round(section.start_distance)}–${Math.round(section.end_distance)} m · ${actionNames[allocation?.action||'none']} · ${allocation?.evidence||'baseline'}${allocation?` · ${Math.round((allocation.applied_fraction??1)*100)}% modeled coverage`:''}`:'Select a section to inspect its action and evidence.';
    if(practice)$('sectionDetail').textContent=allocation?practiceInstruction(allocation):'Select a numbered target to inspect its next test.';
  }
  function renderEvidence() {
    const summary=state.result.model_summary,source=summary.source,entries=state.result.evidence.action_entries;
    $('evidenceSummary').textContent=`${source.eligible_laps} source laps · ${source.sessions} sessions · ${entries.observed||0} observed / ${(entries.inferred||0)+(entries.inferred_baseline||0)} inferred section/action entries. ${state.result.evidence.rejected_action_entries} contradictory actions excluded.`;
    if(state.result.goal==='practice')$('evidenceSummary').textContent=`${source.eligible_laps} source laps · ${source.sessions} sessions · ${state.result.plan.candidate_count} sections with evidence gaps. Priorities use recorded comparisons; no lap-time gains are predicted.`;
    $('conditionNotice').textContent=`Unknown comparison fields: ${summary.selection.unknown_conditions.join(', ') || 'none'}. Known mismatches are excluded; missing fields limit confidence. ${state.result.goal==='practice'?'All compatible valid laps are included; no pace filter or fastest-lap cap.':`Pace window: ${source.pace_window_percent}%.`}`;
    $('excludedNotice').textContent='Excluded laps: '+Object.entries(summary.selection.excluded).filter(([,n])=>n).map(([reason,n])=>`${n} ${reason.replaceAll('_',' ')}`).join(' · ');
    $('assumptionList').replaceChildren(...state.result.assumptions.map(text=>node('li',text)));
    $('sourceRows').replaceChildren(...source.laps.map(lap=>{const row=node('tr');[`${lap.id.split('/')[0]} · Lap ${lap.lap_number}${window.SessionContext.rewindLabel(lap)}`,formatTime(lap.lap_time_ms),lap.conditions.compound||'Unknown',finite(lap.conditions.fuel)?`${Number(lap.conditions.fuel).toFixed(1)} kg`:'Unknown'].forEach(value=>row.append(node('td',value)));return row;}));
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
    // Match the X/Z handedness used by Lap Analysis and the other track maps.
    const project=p=>({x:(w-(maxX-minX)*scale)/2+(p.x-minX)*scale,y:(h-(maxZ-minZ)*scale)/2+(p.z-minZ)*scale});
    const allocations=activeAllocations();ctx.lineCap='round';ctx.lineJoin='round';
    for(let i=1;i<points.length;i++){const a=project(points[i-1]),b=project(points[i]),allocation=allocations.find(r=>points[i].s>=r.start_distance && points[i].s<=r.end_distance);ctx.strokeStyle=colors[allocation?.action||'none'];ctx.lineWidth=6;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
    const selected=result.reference_sections.find(s=>s.number===state.section);if(selected){const p=points.reduce((best,p)=>Math.abs(p.s-(selected.start_distance+selected.end_distance)/2)<Math.abs(best.s-(selected.start_distance+selected.end_distance)/2)?p:best,points[0]),xy=project(p);ctx.strokeStyle='#edf3f4';ctx.lineWidth=2;ctx.beginPath();ctx.arc(xy.x,xy.y,9,0,Math.PI*2);ctx.stroke();}
    if(result.goal==='practice')for(const target of result.plan.targets){const middle=(target.start_distance+target.end_distance)/2,p=points.reduce((best,p)=>Math.abs(p.s-middle)<Math.abs(best.s-middle)?p:best,points[0]),xy=project(p);ctx.fillStyle='#0b1216';ctx.strokeStyle=colors[target.action==='none'?'control':target.action];ctx.lineWidth=2;ctx.beginPath();ctx.arc(xy.x,xy.y,12,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#edf3f4';ctx.textAlign='center';ctx.fillText(String(target.rank),xy.x,xy.y+4);}
    const start=project(points[0]);ctx.fillStyle='#6fe7bf';ctx.beginPath();ctx.arc(start.x,start.y,4,0,Math.PI*2);ctx.fill();
  }
  function drawSoc() {
    if(!state.result || state.result.goal==='practice' || $('planResults').hidden)return;const trace=nextLap()?.soc_trace || [],{ctx,w,h}=canvas('socChart');if(trace.length<2)return;
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
    $('resultTitle').textContent=result.goal==='practice'?'ERS practice map':result.goal==='qualifying'?'Qualifying energy plan':result.goal==='compare'?'Compare energy scenarios':'Next-lap energy plan';
    $('resultContext').textContent=`${track()?.trackName || 'Track'} · ${recordedActivity()} · F1 26 · ${result.plan.start_soc??result.settings.start_soc}% starting battery · ${result.goal==='qualifying'?'0% finish target':`${result.settings.minimum_soc}% reserve`} · ${result.goal==='qualifying'?'Overtake':result.settings.deployment_mode} · built from selected reference lap`;
    $('resultStatus').textContent=state.dirty?'Needs recalculation':result.goal==='qualifying'&&!result.plan.finish_target_reached?'Finish target not reached':'Estimated plan';
    if(result.goal==='practice'){
      $('resultContext').textContent=`${track()?.trackName || 'Track'} · ${recordedActivity()} · ${result.model_summary.source.eligible_laps} comparable source laps · ${actionNames[result.plan.deployment_mode]}`;
      $('resultStatus').textContent=state.dirty?'Needs recalculation':'Data collection suggestions';
    }
    renderScenarios();renderPractice();renderForecast();renderSections();renderEvidence();drawMap();drawSoc();
    if(query.get('panel')==='reference')$('referencePanel').open=true;
  }
  async function build(event) {
    event.preventDefault();if(state.busy || !state.context?.readiness.ready || !$('planForm').reportValidity())return;
    const version=state.version,target=session().id;
    const settings={track_id:track().trackId,selected_lap_id:$('lapSelect').value,goal:state.goal,deployment_mode:$('deploymentMode').value,
      start_soc:state.goal==='practice'?null:state.goal==='qualifying'?100:Number($(state.goal==='race'?'raceStartSoc':'startSoc').value),minimum_soc:state.goal==='qualifying'?0:Number($('reserveSoc').value),horizon:Number($('horizon').value),
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
      state.result=result;state.dirty=Boolean(result.stale);state.section=result.goal==='practice'?result.plan.targets[0]?.section_number??null:null;
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
