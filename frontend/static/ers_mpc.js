(() => {
  const originalParams = window.params;
  const originalLabels = window.updateLabels;
  const originalRender = window.render;
  const originalClear = window.clearResults;
  const byId = id => document.getElementById(id);
  let selectedPlanMode = "boost";
  const planColors = {lift_10: "#ffb05c", lift_20: "#ff9638", lift_30: "#ff7918",
                      boost: "#ffd84d", overtake: "#35a7ff"};

  window.params = function () {
    const value = originalParams();
    value.set("horizon", byId("horizonLaps").value);
    value.set("minimum_finish_soc", byId("minimumSoc").value);
    if (byId("remainingLaps").value) value.set("remaining_laps", byId("remainingLaps").value);
    return value;
  };

  window.updateLabels = function () {
    originalLabels();
    byId("horizonValue").value = `${byId("horizonLaps").value} laps`;
    byId("minimumSocValue").value = `${byId("minimumSoc").value}%`;
  };

  function selectPlanVariant() {
    if (!result) return;
    const scenario = result.scenario_comparisons?.[selectedPlanMode];
    const multiLap = result.multi_lap_strategies?.[selectedPlanMode];
    if (scenario) result.scenario_comparison = scenario;
    if (multiLap) result.multi_lap_strategy = multiLap;
  }

  function renderPlanTabs() {
    document.querySelectorAll("[data-plan-mode]").forEach(button =>
      button.classList.toggle("active", button.dataset.planMode === selectedPlanMode));
    const color = selectedPlanMode === "boost" ? "#ffd84d" : "#35a7ff";
    byId("planModeNotice").textContent = `${selectedPlanMode.toUpperCase()}専用計画 · 同一周回で混在なし`;
    byId("planModeNotice").style.color = color;
  }

  function drawMpcMap(value) {
    const canvas = byId("mpcMap"), points = result?.track_points || [];
    const allocations = value?.current_lap_recommendation?.allocations || [];
    if (!canvas || !points.length) return;
    const rect = canvas.getBoundingClientRect(), ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
    const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const width = rect.width, height = rect.height, pad = 40;
    const xs = points.map(point => point.x), zs = points.map(point => point.z);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minZ = Math.min(...zs), maxZ = Math.max(...zs);
    const scale = Math.min((width - pad * 2) / Math.max(1, maxX - minX),
                           (height - pad * 2) / Math.max(1, maxZ - minZ));
    const ox = (width - (maxX - minX) * scale) / 2, oy = (height - (maxZ - minZ) * scale) / 2;
    const geometry = points.map(point => ({s: point.s, x: ox + (point.x - minX) * scale,
                                           y: oy + (point.z - minZ) * scale}));
    const allocationAt = distance => allocations.find(row => distance >= row.start_distance && distance <= row.end_distance);
    ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#354148"; ctx.lineWidth = 10; ctx.beginPath();
    geometry.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)); ctx.stroke();
    for (let index = 1; index < geometry.length; index++) {
      const row = allocationAt(geometry[index].s); if (!row) continue;
      ctx.strokeStyle = planColors[row.action] || "#aeb8bd"; ctx.lineWidth = 8; ctx.beginPath();
      ctx.moveTo(geometry[index - 1].x, geometry[index -1].y); ctx.lineTo(geometry[index].x, geometry[index].y); ctx.stroke();
    }
    allocations.forEach(row => {
      const target = (row.start_distance + row.end_distance) / 2;
      const point = geometry.reduce((best, candidate) => Math.abs(candidate.s - target) < Math.abs(best.s - target) ? candidate : best, geometry[0]);
      const label = row.action.startsWith("lift_") ? `L${row.action.slice(5)}` : row.action === "overtake" ? "OVTK" : "BOOST";
      ctx.font = "800 8px Inter,system-ui"; const boxWidth = ctx.measureText(label).width + 10;
      ctx.fillStyle = "#071014"; ctx.strokeStyle = planColors[row.action] || "#aeb8bd"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.roundRect(point.x - boxWidth / 2, point.y - 8, boxWidth, 16, 5); ctx.fill(); ctx.stroke();
      ctx.fillStyle = ctx.strokeStyle; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(label, point.x, point.y);
    });
    const used = [...new Set(allocations.map(row => row.action))];
    byId("mpcMapLegend").innerHTML = used.map(action => `<span style="color:${planColors[action]}">${action.replace("_", " ")}</span>`).join("") || "追加操作なし";
  }

  function drawSocChart(value) {
    const canvas = byId("socChart"), lap = value?.current_lap_recommendation;
    const points = lap?.soc_trace || [];
    if (!canvas || points.length < 2) return;
    const rect = canvas.getBoundingClientRect(), ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
    const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const width = rect.width, height = rect.height, left = 48, right = 18, top = 18, bottom = 32;
    const plotWidth = width - left - right, plotHeight = height - top - bottom;
    const trackLength = Math.max(result.track_length_m || 1, ...points.map(point => point.distance));
    const x = distance => left + Math.max(0, Math.min(trackLength, distance)) / trackLength * plotWidth;
    const y = soc => top + (100 - Math.max(0, Math.min(100, soc))) / 100 * plotHeight;
    const floor = Number(value.safety_soc_floor) || 0;

    ctx.fillStyle = "rgba(255,82,99,.12)"; ctx.fillRect(left, y(floor), plotWidth, y(0) - y(floor));
    ctx.font = "10px Inter,system-ui"; ctx.textBaseline = "middle";
    for (const soc of [0, 25, 50, 75, 100]) {
      const py = y(soc); ctx.strokeStyle = soc === floor ? "#ff5263" : "#273238";
      ctx.lineWidth = soc === floor ? 1.5 : 1; ctx.setLineDash(soc === floor ? [5, 4] : []);
      ctx.beginPath(); ctx.moveTo(left, py); ctx.lineTo(width - right, py); ctx.stroke();
      ctx.fillStyle = "#87959a"; ctx.textAlign = "right"; ctx.fillText(`${soc}%`, left - 7, py);
    }
    if (![0, 25, 50, 75, 100].includes(floor)) {
      ctx.strokeStyle = "#ff5263"; ctx.setLineDash([5, 4]); ctx.beginPath();
      ctx.moveTo(left, y(floor)); ctx.lineTo(width - right, y(floor)); ctx.stroke();
    }
    ctx.setLineDash([]);
    for (const fraction of [0, .25, .5, .75, 1]) {
      const distance = trackLength * fraction;
      ctx.fillStyle = "#87959a"; ctx.textAlign = fraction === 0 ? "left" : fraction === 1 ? "right" : "center";
      ctx.fillText(`${(distance / 1000).toFixed(1)} km`, x(distance), height - 11);
    }
    ctx.beginPath(); ctx.moveTo(x(points[0].distance), y(0));
    points.forEach(point => ctx.lineTo(x(point.distance), y(point.soc)));
    ctx.lineTo(x(points[points.length - 1].distance), y(0)); ctx.closePath();
    const gradient = ctx.createLinearGradient(0, top, 0, top + plotHeight);
    gradient.addColorStop(0, "rgba(255,216,77,.34)"); gradient.addColorStop(1, "rgba(255,216,77,.04)");
    ctx.fillStyle = gradient; ctx.fill();
    ctx.beginPath(); points.forEach((point, index) => index ? ctx.lineTo(x(point.distance), y(point.soc)) : ctx.moveTo(x(point.distance), y(point.soc)));
    ctx.strokeStyle = "#ffd84d"; ctx.lineWidth = 2.5; ctx.stroke();
    points.forEach(point => { ctx.fillStyle = planColors[point.action] || "#ffd84d"; ctx.beginPath(); ctx.arc(x(point.distance), y(point.soc), 2.5, 0, Math.PI * 2); ctx.fill(); });
    byId("socChartSummary").textContent = `最低 ${lap.minimum_soc.toFixed(1)}% · 終了 ${lap.soc_end.toFixed(1)}% · 安全下限 ${floor.toFixed(1)}%`;
  }

  function renderMpc() {
    const value = result?.multi_lap_strategy;
    const summary = byId("mpcSummary"), trajectory = byId("mpcTrajectory"), allocations = byId("mpcAllocations");
    if (!value?.analyzable) {
      summary.innerHTML = `<span>${value?.reason || "複数周計画を生成できませんでした"}</span>`;
      trajectory.innerHTML = allocations.innerHTML = ""; return;
    }
    summary.innerHTML = `<span>予測 <b>${value.horizon_laps}周</b></span><span>SOC <b>${value.start_soc.toFixed(1)}% → ${value.predicted_finish_soc.toFixed(1)}%</b></span><span>No deployment比 <b>${Math.round(value.net_gain_vs_no_deployment_ms)} ms短縮</b></span><span>${value.finishing_race ? "最終周まで使い切り" : "次周に再計算"}</span>`;
    if (value.minimum_soc_unreachable) summary.innerHTML += `<span>指定${value.requested_minimum_finish_soc.toFixed(1)}%は到達不能 · 到達可能 ${value.minimum_reachable_soc.toFixed(1)}%</span>`;
    const comparison = result.scenario_comparison, scenarioNote = byId("scenarioConclusion");
    if (comparison?.is_optimized && scenarioNote) scenarioNote.textContent = `${comparison.conclusion} 共通終了SOC ${comparison.common_finish_soc.toFixed(1)}%。区間×操作×SOCのDynamic Programmingで最適化しています。`;
    trajectory.innerHTML = value.trajectory.map((lap, index) => `<article class="mpc-lap ${index === 0 ? "now" : ""}"><header><b>Lap +${index}</b><em>${index === 0 ? "NOW · " : ""}${lap.label}</em></header><strong>SOC ${lap.soc_start.toFixed(1)}% → ${lap.soc_end.toFixed(1)}%</strong><small>${formatTime(lap.predicted_lap_time_ms)} · ΔSOC ${lap.delta_soc > 0 ? "+" : ""}${lap.delta_soc.toFixed(1)}%</small><small>展開 +${Math.round(lap.deployment_gain_ms)} ms · Lift −${Math.round(lap.lifting_loss_ms)} ms</small></article>`).join("");
    allocations.innerHTML = (value.current_lap_recommendation?.allocations || []).map(row => `<span class="${row.action.startsWith("lift_") ? "lift" : row.action}">S${row.section_number} ${row.action.replace("_", " ")} · ${Math.round(row.start_distance)}–${Math.round(row.end_distance)} m · ${Math.round(row.applied_fraction * 100)}%</span>`).join("") || "<span>追加操作なし</span>";
    drawMpcMap(value);
    drawSocChart(value);
  }

  window.render = function () { selectPlanVariant(); originalRender(); renderPlanTabs(); renderMpc(); };
  window.clearResults = function () {
    originalClear(); byId("mpcSummary").innerHTML = byId("mpcTrajectory").innerHTML = byId("mpcAllocations").innerHTML = "";
    byId("scenarioSummary").innerHTML = byId("scenarioAllocations").innerHTML = "";
    byId("scenarioConclusion").textContent = "";
    const map = byId("mpcMap"); if (map) map.getContext("2d").clearRect(0, 0, map.width, map.height);
    const chart = byId("socChart"); if (chart) chart.getContext("2d").clearRect(0, 0, chart.width, chart.height);
    byId("socChartSummary").textContent = "未分析";
    byId("mpcMapLegend").innerHTML = "";
  };

  for (const id of ["horizonLaps", "minimumSoc", "remainingLaps"]) byId(id).oninput = window.scheduleLoad;
  const analyzeButton = byId("analyzeStrategy"), state = byId("mpcState");
  analyzeButton.onclick = async () => {
    analyzeButton.disabled = true; state.textContent = "running";
    await window.loadStrategy();
    state.textContent = result ? "completed" : "failed"; analyzeButton.disabled = false;
  };
  document.querySelectorAll("#trackSelect,#paceWindow,#maxLaps,#windowSize,#horizonLaps,#remainingLaps,#minimumSoc").forEach(element => element.addEventListener("change", () => { state.textContent = "queued · 設定変更あり"; }));
  document.querySelectorAll("[data-plan-mode]").forEach(button => button.onclick = () => {
    selectedPlanMode = button.dataset.planMode;
    if (result) window.render(); else renderPlanTabs();
  });
  renderPlanTabs();
  window.updateLabels();
})();
