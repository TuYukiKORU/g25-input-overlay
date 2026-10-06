const $ = id => document.getElementById(id);
const COLORS = ["#6fe7bf","#ff8a5b","#d98cff","#ffd75e","#58b7ff","#ff6e94","#9fdb63","#ffadcf"];
let hierarchy = [], profiles = [], result = null, selectedCorner = null, refreshTimer = null, editingCorner = null, previewCorner = null, editingEnabled = false;
const query = new URLSearchParams(location.search);

function colorFor(index) { return COLORS[index % COLORS.length]; }
function currentTrack() {
  const session = hierarchy.find(item => item.id === $("sessionSelect").value);
  return session?.tracks.find(track => String(track.trackId) === $("trackSelect").value);
}
function displayCorners() {
  if(!result?.corners)return [];
  const values=result.corners.map(corner=>corner===editingCorner&&previewCorner?{...previewCorner,_preview:true}:{...corner});
  if(!editingCorner&&previewCorner)values.push({...previewCorner,_preview:true});
  values.sort((a,b)=>a.start_distance-b.start_distance);
  return values.map((corner,index)=>({...corner,label:`T${index+1}`}));
}
function updateControlLabels() {
  $("thresholdValue").textContent = Number($("threshold").value).toFixed(4) + " 1/m";
  $("smoothingValue").textContent = `${$("smoothing").value} m`;
  $("minLengthValue").textContent = `${$("minLength").value} m`;
  const threshold = Number($("threshold").value).toFixed(4);
  $("ruleText").textContent = `curvature ≥ +${threshold} or ≤ −${threshold} 1/m for at least ${$("minLength").value} m`;
}
function canvas(id, draw) {
  const element = $(id), rect = element.getBoundingClientRect(), ratio = devicePixelRatio || 1;
  element.width = rect.width * ratio; element.height = rect.height * ratio;
  const ctx = element.getContext("2d"); ctx.scale(ratio, ratio); draw(ctx, rect.width, rect.height);
}
function cornerAt(distance) {
  return displayCorners().find(corner => corner.start_distance <= distance && distance <= corner.end_distance);
}
function drawTrack() {
  canvas("trackMap", (ctx, width, height) => {
    const points = result?.points || []; if (!points.length) return;
    const corners=displayCorners();
    const meanX = points.reduce((sum, point) => sum + point.x, 0) / points.length;
    const meanZ = points.reduce((sum, point) => sum + point.z, 0) / points.length;
    const covariance = points.reduce((value, point) => { const x=point.x-meanX,z=point.z-meanZ; value.xx+=x*x;value.zz+=z*z;value.xz+=x*z;return value; },{xx:0,zz:0,xz:0});
    const angle=.5*Math.atan2(2*covariance.xz,covariance.xx-covariance.zz), cos=Math.cos(angle),sin=Math.sin(angle);
    const rotate=point=>{const x=point.x-meanX,z=point.z-meanZ;return[x*cos+z*sin,-x*sin+z*cos]};
    const rotated=points.map(rotate),xs=rotated.map(p=>p[0]),zs=rotated.map(p=>p[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minZ=Math.min(...zs),maxZ=Math.max(...zs),padding=48;
    const scale=Math.min((width-padding*2)/(maxX-minX||1),(height-padding*2)/(maxZ-minZ||1));
    const ox=(width-(maxX-minX)*scale)/2,oy=(height-(maxZ-minZ)*scale)/2;
    const xy=point=>{const[x,z]=rotate(point);return[ox+(x-minX)*scale,oy+(z-minZ)*scale]};
    ctx.lineJoin="round";ctx.lineCap="round";ctx.strokeStyle="#263037";ctx.lineWidth=20;ctx.beginPath();
    points.forEach((point,index)=>{const[x,y]=xy(point);index?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
    ctx.strokeStyle="#69767c";ctx.lineWidth=3;ctx.stroke();
    points.slice(1).forEach((point,index)=>{const before=points[index],corner=cornerAt((before.s+point.s)/2);if(!corner)return;const cornerIndex=corners.findIndex(value=>value.label===corner.label);ctx.globalAlpha=selectedCorner&&selectedCorner!==corner?.label?.toString()?0.22:1;ctx.strokeStyle=colorFor(cornerIndex);ctx.lineWidth=selectedCorner===corner.label?11:7;const[a,b]=xy(before),[c,d]=xy(point);ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke()});ctx.globalAlpha=1;
    corners.forEach((corner,index)=>{const point=points.reduce((best,p)=>Math.abs(p.s-corner.apex_distance)<Math.abs(best.s-corner.apex_distance)?p:best),[x,y]=xy(point);ctx.fillStyle=colorFor(index);ctx.strokeStyle=corner._preview?"#fff":"#07100e";ctx.lineWidth=corner._preview?4:3;ctx.beginPath();ctx.arc(x,y,selectedCorner===corner.label?15:12,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle="#07100e";ctx.font="bold 10px system-ui";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText(corner.label,x,y+.5)});
  });
}
function drawCurvature() {
  canvas("curvatureChart", (ctx,width,height)=>{const points=result?.points||[];if(!points.length)return;const left=55,right=15,top=15,bottom=30,threshold=Number(result.settings.threshold),end=result.track_length_m;
    const corners=displayCorners();
    const sorted=points.map(point=>point.curvature_abs).sort((a,b)=>a-b),percentile=sorted[Math.floor(sorted.length*.995)]||threshold*2,max=Math.max(threshold*1.6,percentile);
    const graphHeight=height-top-bottom,zeroY=top+graphHeight/2,xFor=s=>left+s/end*(width-left-right),yFor=k=>zeroY-Math.max(-max,Math.min(max,k))/max*graphHeight/2;
    for(const value of[-max,-max/2,0,max/2,max]){const y=yFor(value);ctx.strokeStyle=value===0?"#536168":"#253036";ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();ctx.fillStyle="#89969c";ctx.font="10px system-ui";ctx.textAlign="right";ctx.textBaseline="middle";ctx.fillText(`${value>0?"+":""}${value.toFixed(3)}`,left-7,y)}
    corners.forEach((corner,index)=>{ctx.fillStyle=colorFor(index)+(corner._preview?"66":"33");ctx.fillRect(xFor(corner.start_distance),top,Math.max(2,xFor(corner.end_distance)-xFor(corner.start_distance)),height-top-bottom)});
    const fillSegment=(a,b,value)=>{if(!value)return;ctx.fillStyle=value>0?"rgba(111,231,191,.20)":"rgba(255,138,91,.20)";ctx.beginPath();ctx.moveTo(xFor(a.s),zeroY);ctx.lineTo(xFor(a.s),yFor(a.curvature));ctx.lineTo(xFor(b.s),yFor(b.curvature));ctx.lineTo(xFor(b.s),zeroY);ctx.closePath();ctx.fill()};
    for(let index=1;index<points.length;index++){const a=points[index-1],b=points[index];if(a.curvature*b.curvature<0){const ratio=Math.abs(a.curvature)/(Math.abs(a.curvature)+Math.abs(b.curvature)),crossing={s:a.s+(b.s-a.s)*ratio,curvature:0};fillSegment(a,crossing,a.curvature);fillSegment(crossing,b,b.curvature)}else fillSegment(a,b,a.curvature||b.curvature);ctx.strokeStyle=(a.curvature+b.curvature)/2>=0?"#6fe7bf":"#ff8a5b";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(xFor(a.s),yFor(a.curvature));ctx.lineTo(xFor(b.s),yFor(b.curvature));ctx.stroke()}
    ctx.strokeStyle="#ffd75e";ctx.setLineDash([6,5]);for(const value of[threshold,-threshold]){const y=yFor(value);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();ctx.fillStyle="#ffd75e";ctx.textAlign="left";ctx.fillText(value>0?"+threshold":"−threshold",left+5,y+(value>0?-8:12))}ctx.setLineDash([]);
    corners.forEach((corner,index)=>{const signedPeak=corner.direction==="right"?corner.peak_curvature:-corner.peak_curvature;ctx.fillStyle=colorFor(index);ctx.font="bold 10px system-ui";ctx.textAlign="center";const y=yFor(signedPeak);ctx.fillText(corner.label,xFor(corner.apex_distance),Math.max(top+8,Math.min(height-bottom-5,y+(signedPeak>0?-9:14))))});
    for(let i=0;i<=4;i++){const distance=end*i/4,x=xFor(distance);ctx.fillStyle="#89969c";ctx.textAlign=i===0?"left":i===4?"right":"center";ctx.fillText(`${(distance/1000).toFixed(1)} km`,x,height-8)}
  });
}
function selectCorner(corner) {
  selectedCorner = selectedCorner === corner.label ? null : corner.label;
  $("selectedCorner").textContent = selectedCorner || "All corners";
  document.querySelectorAll(".corner").forEach(row=>row.classList.toggle("selected",row.dataset.label===selectedCorner));drawTrack();drawCurvature();
}
function renderDetected() {
  if(result?.analyzable) $("courseRotation").textContent=result.course_rotation==="clockwise"?"Clockwise":result.course_rotation==="counterclockwise"?"Counterclockwise":"Unknown";
  if(!result?.analyzable){$("message").textContent=`分析不能: ${result?.reason||"unknown"}`;return}
  $("message").textContent="";$("sourceLap").textContent=`Lap ${result.source_lap_number}`;$("cornerCount").textContent=`${result.corners.length}${result.chicanes?.length?` · ${result.chicanes.length} chicane`:""}`;$("trackLength").textContent=`${(result.track_length_m/1000).toFixed(2)} km`;$("sampleCount").textContent=result.sample_count;
  $("cornerList").innerHTML=result.corners.length?result.corners.map((corner,index)=>`<div class="corner" data-label="${corner.label}" style="--corner-color:${colorFor(index)}"><b>${corner.label}</b><span>${Math.round(corner.start_distance)}–${Math.round(corner.end_distance)} m · ${corner.direction}${corner.complex_type==="chicane"?` · CHICANE ${corner.complex_id}`:""}</span><small>Apex ${Math.round(corner.apex_distance)} m · radius ≈ ${corner.radius_m} m</small></div>`).join(""):"<div class=\"empty\">現在の閾値ではコーナーが検出されませんでした。</div>";
  $("cornerList").querySelectorAll(".corner").forEach(row=>row.onclick=()=>selectCorner(result.corners.find(corner=>corner.label===row.dataset.label)));drawTrack();drawCurvature();
}
function rebuildCornerMetadata() {
  result.corners.sort((a,b)=>a.start_distance-b.start_distance);
  result.corners.forEach((corner,index)=>{corner.label=`T${index+1}`;delete corner.complex_type;delete corner.complex_id});
  const chicanes=[];let index=0;
  while(index<result.corners.length-1){const members=[result.corners[index]];let cursor=index;while(cursor+1<result.corners.length){const current=result.corners[cursor],next=result.corners[cursor+1],gap=next.start_distance-current.end_distance,total=next.end_distance-members[0].start_distance;if(current.direction===next.direction||gap>40||total>350)break;members.push(next);cursor++}if(members.length>1){const id=`C${chicanes.length+1}`;members.forEach(corner=>{corner.complex_type="chicane";corner.complex_id=id});chicanes.push({id,type:"chicane",label:`${members[0].label}–${members[members.length-1].label}`,turn_labels:members.map(corner=>corner.label),directions:members.map(corner=>corner.direction),start_distance:members[0].start_distance,end_distance:members[members.length-1].end_distance,transition_gap_m:Math.max(...members.slice(1).map((corner,memberIndex)=>corner.start_distance-members[memberIndex].end_distance))});index=cursor+1}else index++}
  result.chicanes=chicanes;
}
function suggestedCorner() {
  const ordered=[...result.corners].sort((a,b)=>a.start_distance-b.start_distance);let best={start:0,end:result.track_length_m};let previous=0;
  for(const corner of ordered){if(corner.start_distance-previous>best.end-best.start)best={start:previous,end:corner.start_distance};previous=Math.max(previous,corner.end_distance)}
  if(result.track_length_m-previous>best.end-best.start)best={start:previous,end:result.track_length_m};
  const available=Math.max(15,best.end-best.start-10),length=Math.min(120,available),start=Math.max(0,best.start+(best.end-best.start-length)/2),end=Math.min(result.track_length_m,start+length);
  return {start,apex:(start+end)/2,end};
}
function openCornerEditor(index=null) {
  editingCorner=index==null?null:result.corners[index];const corner=editingCorner,suggestion=corner||suggestedCorner();
  $("editorTitle").textContent=corner?`Edit ${corner.label}`:"Add corner";$("cornerStart").value=Number(corner?.start_distance??suggestion.start).toFixed(1);$("cornerApex").value=Number(corner?.apex_distance??suggestion.apex).toFixed(1);$("cornerEnd").value=Number(corner?.end_distance??suggestion.end).toFixed(1);$("cornerDirection").value=corner?.direction||"left";$("deleteCorner").hidden=index==null;$("editorError").hidden=true;$("cornerEditor").hidden=false;$("cornerStart").focus();
  for(const id of["cornerStart","cornerApex","cornerEnd"])$(id).oninput=updateCornerPreview;
  $("cornerDirection").onchange=updateCornerPreview;
  updateCornerPreview();
}
function draftFromInputs(){
  const start=Number($("cornerStart").value),apex=Number($("cornerApex").value),end=Number($("cornerEnd").value);if(![start,apex,end].every(Number.isFinite))return null;
  const point=(result?.points||[]).reduce((best,row)=>!best||Math.abs(row.s-apex)<Math.abs(best.s-apex)?row:best,null),peak=Math.abs(Number(point?.curvature)||0);
  return {start_distance:start,apex_distance:apex,end_distance:end,direction:$("cornerDirection").value,peak_curvature:peak,radius_m:peak>1e-9?Math.round(10/peak)/10:null};
}
function updateCornerPreview(){previewCorner=draftFromInputs();const preview=displayCorners().find(corner=>corner._preview);selectedCorner=preview?.label||null;$("selectedCorner").textContent=preview?`${preview.label} preview`:"All corners";if(result){drawTrack();drawCurvature()}}
function closeCornerEditor(){editingCorner=null;previewCorner=null;selectedCorner=null;$("selectedCorner").textContent="All corners";$("cornerEditor").hidden=true;$("editorError").hidden=true;if(result){drawTrack();drawCurvature()}}
function saveCorner(event) {
  event.preventDefault();const corner=draftFromInputs(),start=corner?.start_distance,apex=corner?.apex_distance,end=corner?.end_distance,others=result.corners.filter(value=>value!==editingCorner);
  let error="";if(![start,apex,end].every(Number.isFinite)||start<0||end>result.track_length_m||!(start<=apex&&apex<=end)||end-start<5)error=`Use 0–${Math.round(result.track_length_m)} m and keep Start ≤ Apex ≤ End (minimum 5 m).`;else if(others.some(corner=>start<corner.end_distance&&end>corner.start_distance))error="This range overlaps another corner.";
  if(error){$("editorError").textContent=error;$("editorError").hidden=false;return}
  if(!editingCorner)result.corners.push(corner);else{const index=result.corners.indexOf(editingCorner);if(index<0){$("editorError").textContent="The corner changed while editing. Open Edit again.";$("editorError").hidden=false;return}result.corners[index]=corner}selectedCorner=null;rebuildCornerMetadata();$("profileStatus").textContent="Unsaved manual changes";closeCornerEditor();render();
}
function deleteEditedCorner(){if(!editingCorner)return;const index=result.corners.indexOf(editingCorner);if(index<0)return;result.corners.splice(index,1);selectedCorner=null;rebuildCornerMetadata();$("profileStatus").textContent="Unsaved manual changes";closeCornerEditor();render()}
function render() {
  if(!result?.analyzable){$("message").textContent=`分析不能: ${result?.reason||"unknown"}`;return}
  $("message").textContent="";$("sourceLap").textContent=`Lap ${result.source_lap_number}`;$("cornerCount").textContent=`${result.corners.length}${result.chicanes?.length?` · ${result.chicanes.length} chicane`:""}`;$("trackLength").textContent=`${(result.track_length_m/1000).toFixed(2)} km`;$("sampleCount").textContent=result.sample_count;
  $("addCorner").hidden=!editingEnabled;
  $("cornerList").innerHTML=result.corners.length?result.corners.map((corner,index)=>`<div class="corner" data-label="${corner.label}" data-index="${index}" style="--corner-color:${colorFor(index)}"><b>${corner.label}</b><span>${Math.round(corner.start_distance)}–${Math.round(corner.end_distance)} m · ${corner.direction}${corner.complex_type==="chicane"?` · CHICANE ${corner.complex_id}`:""}</span><small>Apex ${Math.round(corner.apex_distance)} m · radius ≈ ${corner.radius_m??"—"} m</small><button class="edit-corner" type="button" ${editingEnabled?"":"hidden"}>Edit</button></div>`).join(""):"<div class=\"empty\">No corners are registered. Use Add corner or the curvature controls.</div>";
  $("cornerList").querySelectorAll(".corner").forEach(row=>{row.onclick=()=>selectCorner(result.corners[Number(row.dataset.index)]);row.querySelector(".edit-corner").onclick=event=>{event.stopPropagation();openCornerEditor(Number(row.dataset.index))}});drawTrack();drawCurvature();
}
async function loadSections(useProfile=false) {
  const track=currentTrack();if(!track)return;selectedCorner=null;$("selectedCorner").textContent="All corners";$("message").textContent="Calculating curvature…";
  const params=new URLSearchParams({track_id:track.trackId,threshold:$("threshold").value,smoothing_m:$("smoothing").value,min_length_m:$("minLength").value});
  if(useProfile)params.set("profile","1");
  try{const response=await fetch(`/api/sessions/${encodeURIComponent($("sessionSelect").value)}/track-sections?${params}`,{cache:"no-store"});result=await response.json();if(!response.ok)throw Error(result.error||"Could not calculate track curvature");if(result.profile?.applied){$("threshold").value=result.settings.threshold;$("smoothing").value=result.settings.smoothing_m;$("minLength").value=result.settings.min_length_m;updateControlLabels();$("profileStatus").textContent="Shared track profile · same T numbers across sessions"}else{$("profileStatus").textContent=result.profile?.reason==="track_length_mismatch"?"Saved profile not applied: track length differs":"Unsaved preview"}render()}catch(error){$("message").textContent=error.message}
}
function scheduleLoad(){updateControlLabels();$("profileStatus").textContent="Unsaved preview";clearTimeout(refreshTimer);refreshTimer=setTimeout(()=>loadSections(false),180)}
function sourceSessionFor(profile){return hierarchy.find(session=>session.id===profile?.source_session&&session.tracks.some(track=>String(track.trackId)===String(profile.track_id)))||hierarchy.find(session=>session.tracks.some(track=>String(track.trackId)===String(profile?.track_id)))}
function setSource(session,trackId){if(!session)return false;$("sessionSelect").value=session.id;$("trackSelect").innerHTML=session.tracks.map(track=>`<option value="${track.trackId}">${track.trackName}</option>`).join("");$("trackSelect").value=String(trackId);return Boolean(currentTrack())}
async function selectVerifiedProfile(){const profile=profiles.find(value=>String(value.track_id)===$("verifiedTrackSelect").value);if(!profile)return;const session=sourceSessionFor(profile);if(!setSource(session,profile.track_id)){$("message").textContent="このコースを描画できる保存済みセッションがありません。";return}editingEnabled=false;$("editControls").hidden=true;$("runTurnAnalysis").hidden=true;$("editCorners").hidden=false;$("editCorners").textContent="Edit corners";closeCornerEditor();await loadSections(true)}
function setEditing(enabled){editingEnabled=enabled;$("editControls").hidden=!enabled;$("runTurnAnalysis").hidden=!enabled;$("editCorners").textContent=enabled?"Cancel editing":"Edit corners";if(!enabled){closeCornerEditor();selectVerifiedProfile()}else render()}
async function saveProfile(){const track=currentTrack();if(!track||!result?.corners?.length)return;const button=$("runTurnAnalysis");button.disabled=true;$("analysisLaunchProgress").hidden=false;$("launchProgressText").textContent="Saving shared track profile…";const profileBody={track_length_m:result.track_length_m,settings:result.settings,corners:result.corners,chicanes:result.chicanes,source_session:$("sessionSelect").value,source_lap_id:result.source_lap_id};try{const response=await fetch(`/api/tracks/${encodeURIComponent(track.trackId)}/corner-profile`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(profileBody)});const profile=await response.json();if(!response.ok)throw Error(profile.error||"Could not save shared corner profile");profiles=profiles.filter(value=>String(value.track_id)!==String(profile.track_id));profile.track_name=track.trackName;profiles.push(profile);$("verifiedTrackSelect").innerHTML=profiles.map(value=>`<option value="${value.track_id}">${value.track_name||`Track ${value.track_id}`} · ${value.corners.length} corners</option>`).join("");$("verifiedTrackSelect").value=String(profile.track_id);$("profileStatus").textContent="Saved shared track profile";$("analysisLaunchProgress").hidden=true;button.disabled=false;editingEnabled=false;$("editControls").hidden=true;$("runTurnAnalysis").hidden=true;$("editCorners").hidden=false;$("editCorners").textContent="Edit corners";render()}catch(error){$("message").textContent=error.message;button.disabled=false;$("analysisLaunchProgress").hidden=true}}
async function init(){[hierarchy,profiles]=await Promise.all([fetch("/api/sessions",{cache:"no-store"}).then(response=>response.json()),fetch("/api/track-corner-profiles",{cache:"no-store"}).then(response=>response.json())]);$("sessionSelect").innerHTML=hierarchy.map(session=>`<option value="${session.id}">${SessionContext.sessionLabel(session)}</option>`).join("");const requestedSession=query.get("session"),requestedTrack=query.get("track_id"),registration=query.get("edit")==="1"&&requestedSession&&requestedTrack;$("verifiedTrackSelect").innerHTML=profiles.map(value=>`<option value="${value.track_id}">${value.track_name||`Track ${value.track_id}`} · ${value.corners.length} corners</option>`).join("");$("verifiedTrackSelect").onchange=selectVerifiedProfile;for(const id of["threshold","smoothing","minLength"])$(id).oninput=scheduleLoad;$("resetSettings").onclick=()=>{$("threshold").value=.0066;$("smoothing").value=20;$("minLength").value=15;scheduleLoad()};$("addCorner").onclick=()=>openCornerEditor();$("cornerEditor").onsubmit=saveCorner;$("cancelCorner").onclick=closeCornerEditor;$("deleteCorner").onclick=deleteEditedCorner;$("runTurnAnalysis").onclick=saveProfile;$("editCorners").onclick=()=>setEditing(!editingEnabled);updateControlLabels();if(registration&&!profiles.some(profile=>String(profile.track_id)===requestedTrack)){const session=hierarchy.find(value=>value.id===requestedSession);if(setSource(session,requestedTrack)){$("verifiedTrackSelect").innerHTML+=`<option value="${requestedTrack}">${currentTrack().trackName} · new registration</option>`;$("verifiedTrackSelect").value=requestedTrack;editingEnabled=true;$("editCorners").hidden=true;$("editControls").hidden=false;$("runTurnAnalysis").hidden=false;await loadSections(false)}else $("message").textContent="登録元セッションを読み込めませんでした。"}else if(profiles.length){const chosen=profiles.find(profile=>String(profile.track_id)===requestedTrack)||profiles[0];$("verifiedTrackSelect").value=String(chosen.track_id);await selectVerifiedProfile()}else{$("editCorners").hidden=true;$("message").textContent="検証済みのコースはまだありません。Analysisから登録を開始してください。"}}
init();addEventListener("resize",()=>result&&render());
