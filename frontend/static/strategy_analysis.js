const $ = id => document.getElementById(id);
const kind = document.body.dataset.strategyKind;
const query = new URLSearchParams(location.search);
let hierarchy = [], analysisId = null, pollTimer = null, lastResult = null;
let requestVersion = 0;

function selectionChanged() {
  requestVersion++; clearTimeout(pollTimer);
  $("result").hidden = true; $("statusCard").hidden = true;
  $("analyzeButton").disabled = false;
  $("message").textContent = lastResult ? 'Selection or settings changed. Run Analyze to refresh the result.' : '';
}

const fmt = ms => ms == null ? "—" : `${Math.floor(ms / 60000)}:${((ms % 60000) / 1000).toFixed(3).padStart(6, "0")}`;
const signed = ms => ms == null ? "—" : `${ms >= 0 ? "+" : "−"}${(Math.abs(ms) / 1000).toFixed(3)} s`;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const mapMeta = {
  overtake: {label: "Overtake", short: "OVTK", color: "#35a7ff"},
  boost: {label: "Boost", short: "BOOST", color: "#ffd84d"},
  braking: {label: "Braking", short: "BRAKE", color: "#ff5263"},
  lift: {label: "Lifting", short: "LIFT", color: "#ff9f43"},
  lift_10: {label: "Lift 10%", short: "LIFT10", color: "#ff9f43"},
  lift_20: {label: "Lift 20%", short: "LIFT20", color: "#ff9f43"},
  lift_30: {label: "Lift 30%", short: "LIFT30", color: "#ff9f43"},
  acceleration: {label: "Acceleration", short: "ACCEL", color: "#45d98a"},
  flat_out: {label: "Flat-out", short: "FLAT", color: "#9aa8ae"},
  unknown: {label: "Other / unknown", short: "OTHER", color: "#9aa8ae"},
};

function session() { return hierarchy.find(value => value.id === $("sessionSelect").value); }
function track() { return session()?.tracks.find(value => String(value.trackId) === $("trackSelect").value); }

function renderLaps() {
  const laps = track()?.laps || [];
  $("lapSelect").innerHTML = laps.map(lap => `<option value="${esc(lap.id)}">Lap ${lap.lapNumber} · ${fmt(lap.lapTimeMs)} · ${lap.tyreCompound || "Tyre unknown"}</option>`).join("");
  if (kind === "race" && laps.length) {
    const lap = laps[0];
    if (lap.totalLaps && lap.lapNumber) $("remainingLaps").placeholder = String(Math.max(1, lap.totalLaps - lap.lapNumber + 1));
  }
}

function renderTracks() {
  const value = session();
  $("trackSelect").innerHTML = (value?.tracks || []).map(item => `<option value="${item.trackId}">${esc(item.trackName)}</option>`).join("");
  const selected = SessionContext.chooseTrack(value, query.get("track_id"));
  if (selected) $("trackSelect").value = String(selected.trackId);
  SessionContext.write(value?.id, selected?.trackId);
  renderLaps();
}

function setStatus(status) {
  $("statusCard").hidden = false;
  $("stateBadge").textContent = status.state || "queued";
  $("statusText").textContent = status.current || "分析状態を確認中";
  $("progressBar").value = Number(status.progress) || 0;
  $("progressValue").textContent = `${Number(status.progress) || 0}%`;
  $("errorText").textContent = status.error || "";
  $("analyzeButton").disabled = ["queued", "running"].includes(status.state);
}

function requestBody() {
  const value = {track_id: track().trackId, selected_lap_id: $("lapSelect").value,
                 pace_window_percent: Number($("paceWindow")?.value || 8), force: false};
  const soc = $("socInput").value;
  if (kind === "qualifying") {
    value.start_soc = soc === "" ? null : Number(soc);
    value.minimum_start_line_soc = Number($("minimumStartSoc").value);
    value.minimum_finish_soc = Number($("minimumSoc").value);
  } else {
    value.current_soc = soc === "" ? null : Number(soc);
    value.minimum_soc = Number($("minimumSoc").value);
    value.horizon = Number($("horizon").value);
    value.remaining_laps = $("remainingLaps").value === "" ? null : Number($("remainingLaps").value);
  }
  return value;
}

async function analyze() {
  if (!session() || !track()) return;
  const version = ++requestVersion;
  clearTimeout(pollTimer);
  $("result").hidden = true; $("message").textContent = "";
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(session().id)}/analysis/${kind}`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(requestBody()),
    });
    const status = await response.json();
    if (version !== requestVersion) return;
    if (!response.ok) throw Error(status.error || "分析を開始できませんでした");
    analysisId = status.analysis_id; setStatus(status);
    if (status.state === "completed") await loadResult(version); else poll(version);
  } catch (error) { if (version === requestVersion) {setStatus({state: "failed", error: error.message}); $("analyzeButton").disabled = false;} }
}

async function poll(version) {
  if (version !== requestVersion) return;
  clearTimeout(pollTimer);
  const params = new URLSearchParams({track_id: track().trackId, analysis_id: analysisId});
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(session().id)}/analysis/${kind}/status?${params}`, {cache: "no-store"});
    const status = await response.json();
    if (version !== requestVersion) return;
    if (!response.ok) throw Error(status.error || "状態を取得できませんでした");
    setStatus(status);
    if (status.state === "completed") await loadResult(version);
    else if (["queued", "running"].includes(status.state)) pollTimer = setTimeout(() => poll(version), 700);
  } catch (error) { if (version === requestVersion) {setStatus({state: "failed", error: error.message}); $("analyzeButton").disabled = false;} }
}

async function loadResult(version) {
  const params = new URLSearchParams({track_id: track().trackId, analysis_id: analysisId});
  const response = await fetch(`/api/sessions/${encodeURIComponent(session().id)}/analysis/${kind}/result?${params}`, {cache: "no-store"});
  const value = await response.json();
  if (version !== requestVersion) return;
  if (!response.ok) throw Error(value.error || "結果を取得できませんでした");
  render(value); $("statusCard").hidden = true; $("analyzeButton").disabled = false;
}

function stat(label, value, context = "") {
  return `<article><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(context)}</small></article>`;
}

function ensureStrategyVisuals() {
  if (!document.querySelector('link[href*="strategy_map.css"]')) {
    const link = document.createElement("link"); link.rel = "stylesheet"; link.href = "/static/strategy_map.css";
    link.onload = () => { if (lastResult) drawStrategyMap(lastResult, kind === "qualifying" ? lastResult.general.allocations : lastResult.general.current_lap_recommendation.allocations); };
    document.head.append(link);
  }
  if ($("strategyVisuals")) return;
  const section = document.createElement("section"); section.id = "strategyVisuals"; section.className = "strategy-map-layout";
  section.innerHTML = `<article class="card strategy-map-card"><h2>Recommended operation map</h2><canvas id="strategyMap" aria-label="Recommended ERS and pedal-operation sections"></canvas><div id="strategyMapLegend" class="strategy-map-legend"></div></article><article class="card"><h2>Session ideal lap</h2><div id="idealLapSummary" class="ideal-lap-summary"></div><div id="idealSectionList" class="ideal-section-list"></div></article>`;
  $("result").prepend(section);
}

function displayMode(row) {
  const mode = row.action && row.action !== "none" ? row.action : (row.kind || "flat_out");
  return mapMeta[mode] ? mode : 'unknown';
}

function drawStrategyMap(value, allocations) {
  const points = value.model_summary.track_points || [], canvas = $("strategyMap");
  if (!points.length || !canvas || !allocations.length) return;
  const rect = canvas.getBoundingClientRect(), ratio = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const width = rect.width, height = rect.height, pad = 42;
  const xs = points.map(p => p.x), zs = points.map(p => p.z), minX = Math.min(...xs), maxX = Math.max(...xs), minZ = Math.min(...zs), maxZ = Math.max(...zs);
  const scale = Math.min((width - pad * 2) / Math.max(1, maxX - minX), (height - pad * 2) / Math.max(1, maxZ - minZ));
  const ox = (width - (maxX - minX) * scale) / 2, oy = (height - (maxZ - minZ) * scale) / 2;
  const geometry = points.map(p => ({s: p.s, x: ox + (p.x - minX) * scale, y: oy + (p.z - minZ) * scale}));
  const allocationAt = s => allocations.find(row => s >= row.start_distance && s <= row.end_distance);
  ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#303b40"; ctx.lineWidth = 12; ctx.beginPath();
  geometry.forEach((p, index) => index ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.stroke();
  for (let index = 1; index < geometry.length; index++) {
    const row = allocationAt(geometry[index].s); if (!row) continue;
    const meta = mapMeta[displayMode(row)] || mapMeta.flat_out;
    ctx.strokeStyle = meta.color; ctx.lineWidth = 7; ctx.beginPath(); ctx.moveTo(geometry[index - 1].x, geometry[index - 1].y); ctx.lineTo(geometry[index].x, geometry[index].y); ctx.stroke();
  }
  allocations.forEach(row => {
    const target = (row.start_distance + row.end_distance) / 2;
    const point = geometry.reduce((a, b) => Math.abs(b.s - target) < Math.abs(a.s - target) ? b : a, geometry[0]);
    const meta = mapMeta[displayMode(row)] || mapMeta.flat_out; ctx.font = "800 7px Inter,system-ui";
    const labelWidth = ctx.measureText(meta.short).width + 8; ctx.fillStyle = "#081014"; ctx.strokeStyle = meta.color; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.roundRect(point.x - labelWidth / 2, point.y - 7, labelWidth, 14, 5); ctx.fill(); ctx.stroke();
    ctx.fillStyle = meta.color; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(meta.short, point.x, point.y);
  });
  const used = [...new Set(allocations.map(displayMode))];
  $("strategyMapLegend").innerHTML = used.map(mode => `<span style="--map-color:${mapMeta[mode].color}">${mapMeta[mode].label}</span>`).join("");
}

function renderIdeal(value) {
  const ideal = value.model_summary.ideal_lap || {};
  $("idealLapSummary").innerHTML = ideal.analyzable ? [
    ["Predicted ideal", fmt(ideal.predicted_lap_time_ms)], ["vs session best", signed(ideal.potential_improvement_ms)],
    ["Session best", fmt(ideal.session_best_lap_time_ms)], ["Source laps", ideal.source_lap_count],
  ].map(([label, content]) => `<div><span>${label}</span><strong>${content}</strong></div>`).join("") : '<div><span>Ideal lap</span><strong>Insufficient data</strong></div>';
  $("idealSectionList").innerHTML = (ideal.sections || []).map(row => `<div><b>S${row.section_number}</b><span>${Math.round(row.start_distance)}–${Math.round(row.end_distance)} m · ${esc(row.kind)}<small>Lap ${row.source_lap_number} · ${esc(row.action)}</small></span><strong>${(row.predicted_time_ms / 1000).toFixed(3)} s</strong></div>`).join("");
}

function clipping(rows) {
  $("clippingList").innerHTML = rows.length ? rows.map(row => `<div><span>Section ${row.section_number} · ${Math.round(row.start_distance)}–${Math.round(row.end_distance)} m</span><b>clip ${Math.round(row.clipping_probability * 100)}% · super ${Math.round(row.super_clipping_probability * 100)}%</b></div>`).join("") : '<div><span>しきい値を超える予測地点はありません。</span></div>';
}

function renderQualifying(value) {
  const g = value.general, p = value.personal, ideal = value.model_summary.ideal_lap || {};
  $("summary").innerHTML = [stat("Predicted lap", fmt(g.predicted_lap_time_ms)), stat("Session ideal", fmt(ideal.predicted_lap_time_ms), `${signed(ideal.potential_improvement_ms)} vs best`), stat("Estimated improvement", signed(g.estimated_improvement_ms)), stat("Finish SOC", `${g.predicted_finish_soc.toFixed(1)}%`, `minimum ${g.minimum_finish_soc.toFixed(1)}%`), stat("ERS sections", String(g.recommended_sections.length))].join("");
  $("generalText").textContent = g.recommendation; $("personalText").textContent = p.analyzable ? p.recommendation : p.reason;
  const runupRow = `<div class="strategy-row runup-row"><span>RUN-UP</span><span>最終コーナー出口 → 計測ライン</span><span class="action">overtake ${Math.round((runup.applied_fraction || 0) * 100)}%</span><span class="number">${Number(runup.predicted_soc_cost || 0).toFixed(2)}%</span><span class="number">計測前</span><span class="number">${g.start_line_soc.toFixed(1)}%</span></div>`;
  $("allocationTable").innerHTML = '<div class="strategy-row header"><span>Section</span><span>Range / type</span><span>Mode</span><span>SOC used</span><span>Gain</span><span>Value</span></div>' + runupRow + g.allocations.map(row => `<div class="strategy-row"><span>S${row.section_number}</span><span>${Math.round(row.start_distance)}–${Math.round(row.end_distance)} m · ${esc(row.kind)}</span><span class="action">${esc(row.action)}</span><span class="number">${row.soc_used.toFixed(2)}%</span><span class="number">${Math.round(row.estimated_gain_ms)} ms</span><span class="number">${Number(row.value_ms_per_soc).toFixed(1)} ms/%</span></div>`).join("");
  clipping(g.clipping_predictions); drawStrategyMap(value, g.allocations);
}

function renderRace(value) {
  const g = value.general, p = value.personal, current = g.current_lap_recommendation, ideal = value.model_summary.ideal_lap || {};
  $("summary").innerHTML = [stat("Current lap", current.label, `Lap ${current.lap_number}`), stat("Session ideal", fmt(ideal.predicted_lap_time_ms), `${signed(ideal.potential_improvement_ms)} vs best`), stat("Predicted lap", fmt(current.predicted_lap_time_ms)), stat("Horizon finish SOC", `${g.predicted_finish_soc.toFixed(1)}%`, `target ${g.target_finish_soc.toFixed(1)}%`), stat("vs Sustainable", signed(g.estimated_gain_vs_sustainable_ms), g.soc_shortage_lap ? `SOC shortage Lap ${g.soc_shortage_lap}` : "No SOC shortage")].join("");
  $("generalText").textContent = g.recommendation; $("personalText").textContent = p.analyzable ? p.recommendation : p.reason;
  $("allocationTable").innerHTML = '<div class="strategy-row header"><span>Lap</span><span>Recommendation</span><span>Lap time</span><span>SOC start</span><span>SOC end</span><span>Tyre cost</span></div>' + g.trajectory.map((row, index) => `<div class="strategy-row"><span>${row.lap_number}${index === 0 ? " · NOW" : ""}</span><span class="action">${esc(row.label)}</span><span class="number">${fmt(row.predicted_lap_time_ms)}</span><span class="number">${row.soc_start.toFixed(1)}%</span><span class="number">${row.soc_end.toFixed(1)}%</span><span class="number">${row.tyre_cost.toFixed(2)}</span></div>`).join("");
  clipping(current.clipping_predictions); drawStrategyMap(value, current.allocations);
}

function renderQualifyingOvertake(value) {
  const g = value.general, p = value.personal, ideal = value.model_summary.ideal_lap || {};
  const runup = g.pre_start_runup || {};
  $("summary").innerHTML = [
    stat("ERS mode", "Overtake only", "Boostは予選では使用しません"),
    stat("Before run-up", `${g.battery_before_runup_soc.toFixed(1)}%`, "最終コーナー手前"),
    stat("Start-line SOC", `${g.start_line_soc.toFixed(1)}%`, `最低 ${runup.minimum_start_line_soc?.toFixed(1) || "80.0"}%`),
    stat("Run-up cost", `${Number(runup.predicted_soc_cost || 0).toFixed(2)}%`, `${Math.round((runup.applied_fraction || 0) * 100)}% Overtake`),
    stat("Predicted lap", fmt(g.predicted_lap_time_ms)),
    stat("Session ideal", fmt(ideal.predicted_lap_time_ms), `${signed(ideal.potential_improvement_ms)} vs best`),
    stat("Estimated improvement", signed(g.estimated_improvement_ms)),
    stat("Finish SOC", `${g.predicted_finish_soc.toFixed(1)}%`, `minimum ${g.minimum_finish_soc.toFixed(1)}%`),
  ].join("");
  $("generalText").textContent = g.recommendation;
  $("personalText").textContent = p.analyzable ? p.recommendation : p.reason;
  $("allocationTable").innerHTML = '<div class="strategy-row header"><span>Section</span><span>Range / type</span><span>Mode</span><span>SOC used</span><span>Gain</span><span>Value</span></div>' + g.allocations.map(row => `<div class="strategy-row"><span>S${row.section_number}</span><span>${Math.round(row.start_distance)}–${Math.round(row.end_distance)} m · ${esc(row.kind)}</span><span class="action">${esc(row.action)}</span><span class="number">${row.soc_used.toFixed(2)}%</span><span class="number">${Math.round(row.estimated_gain_ms)} ms</span><span class="number">${Number(row.value_ms_per_soc).toFixed(1)} ms/%</span></div>`).join("");
  clipping(g.clipping_predictions); drawStrategyMap(value, g.allocations);
}

function render(value) {
  lastResult = value; ensureStrategyVisuals(); $("result").hidden = false;
  let notice = $("freshnessNotice");
  if (!notice) {notice = document.createElement('p'); notice.id = 'freshnessNotice'; notice.className = 'card'; $("result").prepend(notice);}
  notice.hidden = !value.stale;
  notice.textContent = value.stale ? 'Saved strategy is outdated: recordings, track definitions or rules changed. Run Analyze again.' : '';
  $("sourceText").textContent = `${value.model_summary.source.eligible_laps} laps · ${value.model_summary.source.sessions} sessions · ${value.model_summary.model_version}`;
  renderIdeal(value); kind === "qualifying" ? renderQualifyingOvertake(value) : renderRace(value);
}

async function init() {
  hierarchy = await fetch("/api/sessions", {cache: "no-store"}).then(response => response.json());
  $("sessionSelect").innerHTML = hierarchy.map(value => `<option value="${esc(value.id)}">${esc(SessionContext.sessionLabel(value))}</option>`).join("");
  const selected = SessionContext.chooseSession(hierarchy, query.get("session")); if (selected) $("sessionSelect").value = selected.id;
  SessionContext.mount($("sessionSelect"), $("trackSelect"));
  $("sessionSelect").onchange = renderTracks;
  $("trackSelect").onchange = () => { SessionContext.write($("sessionSelect").value, $("trackSelect").value); renderLaps(); };
  $("analyzeButton").onclick = analyze; renderTracks();
  $("sessionSelect").addEventListener('change', selectionChanged);
  $("trackSelect").addEventListener('change', selectionChanged);
  document.querySelector('.strategy-controls').addEventListener('input', selectionChanged);
  document.querySelector('.strategy-controls').addEventListener('change', selectionChanged);
  setInterval(async () => {
    if (!lastResult || document.hidden || $("result").hidden) return;
    const version = requestVersion;
    try {
      const params = new URLSearchParams({track_id: track().trackId, analysis_id: analysisId});
      const response = await fetch(`/api/sessions/${encodeURIComponent(session().id)}/analysis/${kind}/status?${params}`, {cache:'no-store'});
      if (!response.ok || version !== requestVersion) return;
      const status = await response.json();
      if (version !== requestVersion) return;
      $("freshnessNotice").hidden = !status.stale;
      $("freshnessNotice").textContent = status.stale ? 'Saved strategy is outdated. Run Analyze again to use current recordings and rules.' : '';
    } catch { /* Keep the displayed result during connection failures. */ }
  }, 15000);
}

addEventListener("resize", () => {
  if (!lastResult || $("result").hidden) return;
  const allocations = kind === "qualifying" ? lastResult.general.allocations : lastResult.general.current_lap_recommendation.allocations;
  drawStrategyMap(lastResult, allocations);
});
init().catch(error => $("message").textContent = error.message);
