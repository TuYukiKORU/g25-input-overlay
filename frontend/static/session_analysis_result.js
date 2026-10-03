const $ = id => document.getElementById(id);
const query = new URLSearchParams(location.search);
const session = query.get("session");
const trackId = query.get("track_id");
let result = null, pollTimer = null;

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character]));
const signedSeconds = value => value == null ? "—" : `${Number(value) > 0 ? "+" : Number(value) < 0 ? "−" : ""}${(Math.abs(Number(value)) / 1000).toFixed(3)} s`;
const metric = (value, unit, digits = 1) => value == null ? "—" : `${Number(value).toFixed(digits)} ${unit}`;

function setStatus(status) {
  const state = status.state || "queued";
  $("stateBadge").className = `state ${state}`;
  $("stateBadge").textContent = state;
  $("statusText").textContent = status.current || "分析状態を確認しています…";
  $("progressBar").value = Number(status.progress) || 0;
  $("progressValue").textContent = `${Number(status.progress) || 0}%`;
  $("errorText").hidden = state !== "failed";
  $("errorText").textContent = status.error ? `分析失敗: ${status.error}` : "";
}

function comparisonValue(selected, compared, key, unit, digits = 1) {
  const selectedText = metric(selected?.[key], unit, digits);
  const comparedText = metric(compared?.[key], unit, digits);
  return `<b>${selectedText}</b><small>比較 ${comparedText}</small>`;
}

function renderResult(value) {
  result = value;
  $("freshnessNotice").hidden = !value.stale;
  $("freshnessNotice").textContent = value.stale ? `${value.freshness_reason || 'Saved analysis is outdated.'} Use Reanalyze below.` : '';
  const adjustParams = new URLSearchParams({session, track_id: trackId});
  if (value.selected_lap_id) adjustParams.set("selected_lap_id", value.selected_lap_id);
  $("adjustLink").href = `/map-corners?${adjustParams}`;
  $("resultContent").hidden = false;
  $("coordinateNotice").hidden = value.coordinate_mode !== 'planar_xz';
  $("coordinateNotice").textContent = 'Planar track analysis: these recordings lack measured elevation. All laps use their recorded X/Z positions.';
  $("statusCard").hidden = true;
  $("targetLabel").textContent = `Lap ${value.selected_lap_number ?? "—"} vs Lap ${value.comparison_lap_number ?? "—"}`;
  if (value.comparison_context) {
    $("targetLabel").textContent += ` · ${value.comparison_context.label} · ${value.comparison_context.notes.join(' · ')}`;
  }
  const counts = value.sample_counts || {}, confidence = value.confidence || {}, turnSummary = value.turn_summary || {};
  $("summary").innerHTML = [
    ["Selected / comparison", `Lap ${value.selected_lap_number ?? "—"} / Lap ${value.comparison_lap_number ?? "—"}`],
    ["Detected turns delta", signedSeconds(turnSummary.total_delta_ms)],
    ["Turn improvement potential", signedSeconds(turnSummary.total_potential_loss_ms)],
    ["Loss / gain turns", `${turnSummary.loss_count || 0} / ${turnSummary.gain_count || 0}`],
    ["Confidence", `${escapeHtml(confidence.label || "—")} ${Math.round(Number(confidence.score || 0) * 100)}%`],
    ["Samples", `${counts.eligible_laps || 0} eligible laps`],
  ].map(([label, content]) => `<article><span>${label}</span><strong>${content}</strong></article>`).join("");
  if (!value.analyzable) {
    $("unavailable").hidden = false;
    $("unavailable").textContent = `分析不能: ${value.reason || "比較可能なデータが不足しています"}`;
    $("turnList").innerHTML = "";
    return;
  }
  $("unavailable").hidden = true;
  const turns = value.turns || [];
  $("turnList").innerHTML = turns.length ? turns.map(turn => {
    const selected = turn.selected || {}, compared = turn.comparison || {};
    const eventLabel = selected.events?.length ? selected.events.map(event => event === "wheel_spin" ? "Wheel spin" : event === "tyre_lock" ? "Tyre lock" : event).join(" / ") : "No spin or lock detected";
    const complex = turn.complex_type === "chicane" ? ` · ${turn.complex_id || "Chicane"}` : "";
    return `<article class="card turn ${escapeHtml(turn.outcome || "neutral")}">
      <div class="turn-title"><strong>${escapeHtml(turn.label)}</strong><small>${escapeHtml(turn.direction || "")} ${Math.round(Number(turn.start_distance))}–${Math.round(Number(turn.end_distance))} m${escapeHtml(complex)}</small><small>Best sector: Lap ${escapeHtml(turn.best_lap_number)}</small></div>
      <div class="delta"><span>Time loss / gain</span><strong>${signedSeconds(turn.time_delta_ms)}</strong><small>Potential ${signedSeconds(turn.potential_loss_ms)}</small></div>
      <div class="metrics">
        <div class="metric"><span>Entry speed</span>${comparisonValue(selected, compared, "entry_speed_kph", "km/h")}</div>
        <div class="metric"><span>Apex speed</span>${comparisonValue(selected, compared, "apex_speed_kph", "km/h")}</div>
        <div class="metric"><span>Exit speed</span>${comparisonValue(selected, compared, "exit_speed_kph", "km/h")}</div>
        <div class="metric"><span>Exit acceleration</span>${comparisonValue(selected, compared, "exit_acceleration_g", "G", 2)}</div>
        <div class="metric"><span>Peak slip</span>${comparisonValue(selected, compared, "peak_slip", "", 3)}</div>
      </div>
      <div class="coaching"><b>${escapeHtml(turn.primary_cause)}</b><span>${escapeHtml(turn.suggestion)}</span><span class="event">${escapeHtml(eventLabel)}</span><span class="confidence">Confidence ${escapeHtml(turn.confidence?.label || "—")} ${Math.round(Number(turn.confidence?.score || 0) * 100)}% · ${turn.sample_count || 0} laps</span></div>
    </article>`;
  }).join("") : `<article class="card unavailable">設定した閾値ではターンを検出できませんでした。Adjust turns から設定を見直してください。</article>`;
}

async function fetchResult() {
  const response = await fetch(`/api/sessions/${encodeURIComponent(session)}/analysis/result?track_id=${encodeURIComponent(trackId)}`, {cache: "no-store"});
  const body = await response.json();
  if (!response.ok) throw Error(body.error || "分析結果を取得できませんでした");
  renderResult(body);
}

async function poll() {
  clearTimeout(pollTimer);
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(session)}/analysis/status?track_id=${encodeURIComponent(trackId)}`, {cache: "no-store"});
    const status = await response.json();
    if (!response.ok) throw Error(status.error || "分析状態を取得できませんでした");
    setStatus(status);
    if (status.state === "completed") await fetchResult();
    else if (status.state === "queued" || status.state === "running") pollTimer = setTimeout(poll, 800);
  } catch (error) { setStatus({state: "failed", progress: 0, error: error.message}); }
}

async function reanalyze() {
  const settings = result?.turn_definition?.settings || {threshold: .0066, smoothing_m: 20, min_length_m: 15};
  $("resultContent").hidden = true; $("statusCard").hidden = false;
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(session)}/analysis`, {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({track_id: trackId, selected_lap_id: result?.selected_lap_id, section_settings: settings, force: true})});
    const status = await response.json(); if (!response.ok) throw Error(status.error || "再分析を開始できませんでした");
    setStatus(status); poll();
  } catch (error) { setStatus({state: "failed", progress: 0, error: error.message}); }
}

function init() {
  if (!session || trackId == null) { setStatus({state: "failed", progress: 0, error: "session と track_id が必要です"}); return; }
  const params = new URLSearchParams({session, track_id: trackId});
  if (query.get("selected_lap_id")) params.set("selected_lap_id", query.get("selected_lap_id"));
  $("adjustLink").href = `/map-corners?${params}`;
  $("reanalyze").onclick = reanalyze;
  poll();
  setInterval(async () => {
    if (!result || document.hidden || !$("statusCard").hidden) return;
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(session)}/analysis/status?track_id=${encodeURIComponent(trackId)}`, {cache: "no-store"});
      if (!response.ok) return;
      const status = await response.json();
      $("freshnessNotice").hidden = !status.stale;
      $("freshnessNotice").textContent = status.stale ? `${status.freshness_reason} Use Reanalyze below.` : '';
    } catch { /* Keep the displayed result when the connection is unavailable. */ }
  }, 15000);
}

init();
