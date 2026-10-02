const $ = id => document.getElementById(id);
let lap, analysis, reference, comparisonAnalysis, hoverDistance = null, knownLatest = null;
let sessionAnalysis = null, selectedSection = null, analysisPollTimer = null, trackHitPoints = [];
let lapsCache = [], selectedLapId = null, comparisonLapId = null;
let chartZoom = null;
let lapLoadVersion = 0;

function distanceRange(end) { return chartZoom || {start: 0, end}; }
function zoomToSection(section) {
  if (!lap) return;
  selectedSection = section;
  const end = Math.max(...lap.samples.map(s => Number(s.lap_distance) || 0), 1);
  chartZoom = section ? {start: Math.max(0, section.start_distance - 60), end: Math.min(end, section.end_distance + 80)} : null;
  hoverDistance = section ? (section.start_distance + section.end_distance) / 2 : null;
  if ($("zoomStatus")) $("zoomStatus").textContent = chartZoom ? `${Math.round(chartZoom.start)}–${Math.round(chartZoom.end)} m · charts and driving lines` : 'Full lap';
  if ($("resetZoom")) $("resetZoom").disabled = !chartZoom;
  plot();
}
window.zoomAnalysisSection = zoomToSection;
const TIME_AXIS_LEFT = 112, TIME_AXIS_RIGHT = 10, TIME_AXIS_TOP = 58, TIME_AXIS_BOTTOM = 28;
const SELECTED_COLOR = "#40cfff", COMPARISON_COLOR = "#ff9f68";

function time(ms) {
  if (!ms) return "—";
  return `${Math.floor(ms / 60000)}:${((ms % 60000) / 1000).toFixed(3).padStart(6, "0")}`;
}

function signedTime(ms) {
  const value = Number(ms) || 0, absolute = Math.abs(value);
  const formatted = `${Math.floor(absolute / 60000)}:${((absolute % 60000) / 1000).toFixed(3).padStart(6, "0")}`;
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatted}`;
}

function isSeasonPack(value) {
  return value?.packetFormat === 2026 || value?.gameYear === 26 || value?.gameVersion === "F1 26" || value?.udpMode === "2026 Season Pack";
}

function gameVersionLabel(value) {
  if (value?.editionDetection === "legacy_udp_unconfirmed") return "F1 25 UDP · EDITION UNCONFIRMED";
  return isSeasonPack(value) ? "F1 25 · 2026 SEASON PACK" : "F1 25";
}

function tyreSummary(value) {
  if (!value) return "";
  const compound = value.tyreCompound || "Tyre unknown";
  const age = value.tyreAgeLapsAtStart;
  return age == null ? compound : `${compound} · ${age} laps`;
}

function setLapBoxStatus(id, status) {
  const box = $(id);
  box.classList.remove("lap-status-fastest", "lap-status-faster", "lap-status-slower", "lap-status-solo");
  box.classList.add(`lap-status-${status}`);
}

function updateComparisonSummary() {
  const session = $("sessionSelect").value;
  const items = lapsCache.filter(item => (item.session || "Legacy session") === session);
  const valid = items.filter(item => item.validLap && Number(item.lapTimeMs) > 0);
  const best = valid.reduce((fastest, item) => !fastest || item.lapTimeMs < fastest.lapTimeMs ? item : fastest, null);
  const selectedIsBest = selectedLapId === best?.id;
  if (!reference) {
    setLapBoxStatus("selectedLapBox", selectedIsBest ? "fastest" : "solo");
    setLapBoxStatus("comparisonLapBox", selectedIsBest ? "fastest" : "solo");
    $("totalDelta").textContent = "";
    $("totalDelta").style.color = "";
    return;
  }
  const comparisonIsBest = comparisonLapId === best?.id;
  const selectedFaster = Number(lap.lapTimeMs) <= Number(reference.lapTimeMs);
  const selectedStatus = selectedIsBest ? "fastest" : selectedFaster ? "faster" : "slower";
  const comparisonStatus = comparisonIsBest ? "fastest" : selectedFaster ? "slower" : "faster";
  setLapBoxStatus("selectedLapBox", selectedStatus);
  setLapBoxStatus("comparisonLapBox", comparisonStatus);
  $("totalDelta").textContent = signedTime(Number(lap.lapTimeMs) - Number(reference.lapTimeMs));
  $("totalDelta").style.color = selectedStatus === "fastest" ? "#c16cff" : selectedStatus === "faster" ? "#52e08a" : "#ffd84d";
}

function canvas(id, draw) {
  const element = $(id), rect = element.getBoundingClientRect(), ratio = devicePixelRatio || 1;
  if (!rect.width || !rect.height) return;
  element.width = rect.width * ratio; element.height = rect.height * ratio;
  const ctx = element.getContext("2d"); ctx.scale(ratio, ratio);
  draw(ctx, rect.width, rect.height);
}

function nearest(points, distance, field = "distance") {
  if (!points.length) return null;
  return points.reduce((a, b) => Math.abs(b[field] - distance) < Math.abs(a[field] - distance) ? b : a);
}

function niceStep(value) {
  const power = 10 ** Math.floor(Math.log10(Math.max(value, 1)));
  const fraction = value / power;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return niceFraction * power;
}

function drawSectionHighlight(ctx, xFor, top, bottom) {
  if (!selectedSection) return;
  const start = xFor(selectedSection.start_distance), end = xFor(selectedSection.end_distance);
  ctx.save(); ctx.fillStyle = "rgba(255,75,75,.16)"; ctx.strokeStyle = "rgba(255,107,114,.9)"; ctx.lineWidth = 1;
  ctx.fillRect(start, top, Math.max(2, end - start), bottom - top); ctx.strokeRect(start, top, Math.max(2, end - start), bottom - top); ctx.restore();
}

function graphSamples(value) {
  return (value?.samples || []).filter(sample => sample.lap_distance != null && sample.lap_time_ms != null && Number.isFinite(Number(sample.lap_distance)) && Number.isFinite(Number(sample.lap_time_ms)) && (!chartZoom || (sample.lap_distance >= chartZoom.start && sample.lap_distance <= chartZoom.end))).sort((a, b) => a.lap_distance - b.lap_distance);
}

function usageIntervals(samples, isActive) {
  const intervals = []; let start = null, last = null;
  for (const sample of samples) {
    if (isActive(sample)) { if (start == null) start = Number(sample.lap_distance); last = Number(sample.lap_distance); }
    else if (start != null) { intervals.push([start, last]); start = null; last = null; }
  }
  if (start != null) intervals.push([start, last]);
  return intervals;
}

function inputPercent(sample, key) {
  const value = Number(sample?.[key]) || 0;
  return Math.max(0, Math.min(100, value <= 1 ? value * 100 : value));
}

function samplesWithAcceleration(value) {
  const points = graphSamples(value).filter(point => Number.isFinite(Number(point.speed)));
  return points.map((point, index) => {
    const recorded = Number(point.longitudinal_g);
    if (point.longitudinal_g != null && Number.isFinite(recorded)) return {...point, acceleration_g: recorded};
    const before = points[Math.max(0, index - 2)], after = points[Math.min(points.length - 1, index + 2)];
    const elapsed = (Number(after.lap_time_ms) - Number(before.lap_time_ms)) / 1000;
    const derived = elapsed > 0 ? ((Number(after.speed) - Number(before.speed)) / 3.6) / elapsed / 9.80665 : 0;
    return {...point, acceleration_g: Math.max(-6, Math.min(6, derived))};
  });
}

function drawSpeedChart() {
  $("speedChart").style.height = innerWidth <= 700 ? "300px" : "320px";
  canvas("speedChart", (ctx, width, height) => {
    const selected = graphSamples(lap).filter(point => Number.isFinite(Number(point.speed)));
    const fastest = graphSamples(reference).filter(point => Number.isFinite(Number(point.speed)));
    if (!selected.length) return;
    const all = [...selected, ...fastest], end = Math.max(...all.map(point => Number(point.lap_distance)), 1);
    const dataMax = Math.max(...all.map(point => Number(point.speed)), 1);
    const step = niceStep(dataMax / 5), max = Math.ceil(dataMax / step) * step;
    const graphWidth = width - TIME_AXIS_LEFT - TIME_AXIS_RIGHT, graphHeight = height - TIME_AXIS_TOP - TIME_AXIS_BOTTOM;
    const range = distanceRange(end), span = Math.max(1, range.end - range.start);
    const xFor = distance => TIME_AXIS_LEFT + (Number(distance) - range.start) / span * graphWidth;
    const yFor = speed => height - TIME_AXIS_BOTTOM - Number(speed) / max * graphHeight;
    ctx.font = "11px system-ui, sans-serif"; ctx.textBaseline = "middle";
    for (let value = 0; value <= max; value += step) {
      const y = yFor(value); ctx.strokeStyle = value === 0 ? "#56636b" : "#293137"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(TIME_AXIS_LEFT, y); ctx.lineTo(width - TIME_AXIS_RIGHT, y); ctx.stroke();
      ctx.fillStyle = "#aeb9bf"; ctx.textAlign = "right"; ctx.fillText(`${Math.round(value)} km/h`, TIME_AXIS_LEFT - 7, y);
    }
    for (let index = 0; index <= 4; index++) {
      const distance = range.start + span * index / 4, x = xFor(distance);
      ctx.strokeStyle = "#293137"; ctx.beginPath(); ctx.moveTo(x, TIME_AXIS_TOP); ctx.lineTo(x, height - TIME_AXIS_BOTTOM); ctx.stroke();
      ctx.fillStyle = "#aeb9bf"; ctx.textAlign = index === 0 ? "left" : index === 4 ? "right" : "center"; ctx.textBaseline = "bottom";
      ctx.fillText(distance >= 1000 ? `${(distance / 1000).toFixed(1)} km` : `${Math.round(distance)} m`, x, height - 4);
    }
    drawSectionHighlight(ctx, xFor, TIME_AXIS_TOP, height - TIME_AXIS_BOTTOM);
    const drawUsageBands = (intervals, color, y) => {
      ctx.fillStyle = color;
      for (const [start, finish] of intervals) ctx.fillRect(xFor(start), y, Math.max(2, xFor(finish) - xFor(start)), 8);
    };
    const drawOwnerLabel = (label, y) => { ctx.fillStyle = "#c8d1d5"; ctx.font = "bold 11px system-ui, sans-serif"; ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(label, TIME_AXIS_LEFT - 7, y + 4); };
    const drawLapUsage = (points, metadata, aeroY, ersY, owner, opacity) => {
      const seasonPack = isSeasonPack(metadata);
      const aeroActive = point => seasonPack ? Boolean(point.active_aero) : Number(point.drs) > 0;
      const boostActive = point => seasonPack ? Number(point.boost_active) > 0 && Number(point.overtake_active) === 0 : Boolean(point.ers_usage);
      const overtakeActive = point => seasonPack && Number(point.overtake_active) > 0;
      drawUsageBands(usageIntervals(points, aeroActive), seasonPack ? `rgba(255,75,140,${opacity})` : `rgba(82,224,138,${opacity})`, aeroY);
      drawUsageBands(usageIntervals(points, boostActive), `rgba(255,216,77,${opacity})`, ersY);
      drawUsageBands(usageIntervals(points, overtakeActive), `rgba(53,167,255,${opacity})`, ersY);
      drawOwnerLabel(`${owner} ${seasonPack ? "AERO" : "DRS"}`, aeroY);
      drawOwnerLabel(`${owner} ERS`, ersY);
    };
    drawLapUsage(selected, lap, 5, 17, "SELECTED", .85);
    if (fastest.length) drawLapUsage(fastest, reference, 31, 43, "COMPARE", .55);
    const drawSeries = (points, color, lineWidth) => {
      if (!points.length) return;
      ctx.strokeStyle = color; ctx.lineWidth = lineWidth; ctx.lineJoin = "round"; ctx.beginPath();
      points.forEach((point, index) => { const x = xFor(point.lap_distance), y = yFor(point.speed); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      ctx.stroke();
    };
    drawSeries(fastest, COMPARISON_COLOR, 2.5); drawSeries(selected, SELECTED_COLOR, 2.5);
    if (hoverDistance != null) {
      const x = xFor(hoverDistance); ctx.strokeStyle = "rgba(255,255,255,.55)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, TIME_AXIS_TOP); ctx.lineTo(x, height - TIME_AXIS_BOTTOM); ctx.stroke();
      const hoverValues = [];
      for (const [points, color, label] of [[selected, SELECTED_COLOR, "Selected"], [fastest, COMPARISON_COLOR, "Comparison"]]) {
        const point = nearest(points, hoverDistance, "lap_distance"); if (!point) continue;
        ctx.fillStyle = color; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(xFor(point.lap_distance), yFor(point.speed), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        hoverValues.push({label, color, speed: Math.round(Number(point.speed)), y: yFor(point.speed)});
      }
      if (hoverValues.length) {
        const boxWidth = 136, lineHeight = 18, boxHeight = hoverValues.length * lineHeight + 8;
        const boxX = x + boxWidth + 12 > width ? x - boxWidth - 12 : x + 12;
        const anchorY = hoverValues[0].y, boxY = Math.max(TIME_AXIS_TOP, Math.min(height - TIME_AXIS_BOTTOM - boxHeight, anchorY - boxHeight / 2));
        ctx.fillStyle = "rgba(8,11,14,.92)"; ctx.strokeStyle = "#56636b"; ctx.lineWidth = 1; ctx.fillRect(boxX, boxY, boxWidth, boxHeight); ctx.strokeRect(boxX, boxY, boxWidth, boxHeight);
        ctx.font = "bold 11px system-ui, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
        hoverValues.forEach((value, index) => { ctx.fillStyle = value.color; ctx.fillText(`${value.label}: ${value.speed} km/h`, boxX + 8, boxY + 7 + lineHeight * (index + .5)); });
      }
    }
  });
}

function drawDistanceGrid(ctx, width, height, end, left, right, top, bottom) {
  const range = distanceRange(end), span = Math.max(1, range.end - range.start);
  const xFor = distance => left + (Number(distance) - range.start) / span * (width - left - right);
  for (let index = 0; index <= 4; index++) {
    const distance = range.start + span * index / 4, x = xFor(distance);
    ctx.strokeStyle = "#293137"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, height - bottom); ctx.stroke();
    ctx.fillStyle = "#aeb9bf"; ctx.font = "11px system-ui, sans-serif"; ctx.textAlign = index === 0 ? "left" : index === 4 ? "right" : "center"; ctx.textBaseline = "bottom";
    ctx.fillText(distance >= 1000 ? `${(distance / 1000).toFixed(1)} km` : `${Math.round(distance)} m`, x, height - 4);
  }
  return xFor;
}

function drawMetricSeries(ctx, points, valueFor, xFor, yFor, color, dashed = false, alpha = 1) {
  if (!points.length) return;
  ctx.save(); ctx.globalAlpha = alpha; ctx.strokeStyle = color; ctx.lineWidth = dashed ? 1.5 : 2.2;
  ctx.lineJoin = "round"; ctx.setLineDash(dashed ? [7, 5] : []); ctx.beginPath();
  points.forEach((point, index) => {
    const x = xFor(point.lap_distance), y = yFor(valueFor(point));
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke(); ctx.restore();
}

function drawMetricHover(ctx, width, x, top, bottomY, values, boxWidth = 190) {
  ctx.strokeStyle = "rgba(255,255,255,.55)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottomY); ctx.stroke();
  if (!values.length) return;
  const boxHeight = values.length * 20 + 10, boxX = x + boxWidth + 12 > width ? x - boxWidth - 12 : x + 12, boxY = top + 8;
  ctx.fillStyle = "rgba(8,11,14,.94)"; ctx.strokeStyle = "#56636b"; ctx.fillRect(boxX, boxY, boxWidth, boxHeight); ctx.strokeRect(boxX, boxY, boxWidth, boxHeight);
  ctx.font = "bold 11px system-ui, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
  values.forEach((value, index) => { ctx.fillStyle = index ? "#b9c2c6" : "#eef2f4"; ctx.fillText(value, boxX + 8, boxY + 15 + index * 20); });
}

function drawAccelerationChart() {
  $("accelerationChart").style.height = innerWidth <= 700 ? "250px" : "270px";
  canvas("accelerationChart", (ctx, width, height) => {
    const selected = samplesWithAcceleration(lap);
    const fastest = samplesWithAcceleration(reference);
    if (!selected.length) return;
    const all = [...selected, ...fastest], end = Math.max(...all.map(point => Number(point.lap_distance)), 1);
    const selectedBattery = selected.filter(point => point.ers_percent != null && Number.isFinite(Number(point.ers_percent)));
    const comparisonBattery = fastest.filter(point => point.ers_percent != null && Number.isFinite(Number(point.ers_percent)));
    const left = 62, right = 52, top = 15, bottom = TIME_AXIS_BOTTOM, graphHeight = height - top - bottom;
    const peak = Math.max(1, ...all.map(point => Math.abs(Number(point.acceleration_g) || 0)));
    const maxG = Math.max(1, Math.ceil(Math.min(6, peak) * 2) / 2);
    const yFor = value => top + (maxG - Number(value)) / (maxG * 2) * graphHeight;
    const batteryYFor = value => height - bottom - Math.max(0, Math.min(100, Number(value))) / 100 * graphHeight;
    ctx.font = "11px system-ui, sans-serif"; ctx.textBaseline = "middle";
    for (const value of [-maxG, -maxG / 2, 0, maxG / 2, maxG]) {
      const y = yFor(value); ctx.strokeStyle = value === 0 ? "#56636b" : "#293137"; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
      ctx.fillStyle = "#aeb9bf"; ctx.textAlign = "right"; ctx.fillText(`${value > 0 ? "+" : ""}${value.toFixed(1)} G`, left - 6, y);
    }
    const xFor = drawDistanceGrid(ctx, width, height, end, left, right, top, bottom);
    drawSectionHighlight(ctx, xFor, top, height - bottom);
    const drawBatteryArea = points => {
      if (!points.length) return;
      ctx.beginPath(); ctx.moveTo(xFor(points[0].lap_distance), height - bottom);
      points.forEach(point => ctx.lineTo(xFor(point.lap_distance), batteryYFor(point.ers_percent)));
      ctx.lineTo(xFor(points[points.length - 1].lap_distance), height - bottom); ctx.closePath();
      ctx.fillStyle = "rgba(255,216,77,.14)"; ctx.fill();
    };
    const drawBatteryLine = (points, dashed = false, alpha = 1) => {
      if (!points.length) return;
      ctx.save(); ctx.globalAlpha = alpha; ctx.lineJoin = "round"; ctx.lineWidth = dashed ? 1.5 : 2;
      ctx.strokeStyle = "#ffd84d"; ctx.setLineDash(dashed ? [7, 5] : []); ctx.beginPath();
      points.forEach((point, index) => {
        const x = xFor(point.lap_distance), y = batteryYFor(point.ers_percent);
        index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke(); ctx.restore();
    };
    const batteryAt = (points, distance) => {
      if (!points.length || distance < Number(points[0].lap_distance) || distance > Number(points[points.length - 1].lap_distance)) return null;
      let low = 0, high = points.length - 1;
      while (low <= high) {
        const middle = Math.floor((low + high) / 2), current = Number(points[middle].lap_distance);
        if (current === distance) return Math.max(0, Math.min(100, Number(points[middle].ers_percent)));
        if (current < distance) low = middle + 1; else high = middle - 1;
      }
      const before = points[Math.max(0, high)], after = points[Math.min(points.length - 1, low)];
      const span = Number(after.lap_distance) - Number(before.lap_distance);
      const ratio = span > 0 ? (distance - Number(before.lap_distance)) / span : 0;
      return Math.max(0, Math.min(100, Number(before.ers_percent) + (Number(after.ers_percent) - Number(before.ers_percent)) * ratio));
    };
    const drawBatteryDifference = () => {
      if (!selectedBattery.length || !comparisonBattery.length) return;
      const start = Math.max(Number(selectedBattery[0].lap_distance), Number(comparisonBattery[0].lap_distance));
      const finish = Math.min(Number(selectedBattery[selectedBattery.length - 1].lap_distance), Number(comparisonBattery[comparisonBattery.length - 1].lap_distance));
      const distances = [...new Set([...selectedBattery, ...comparisonBattery].map(point => Number(point.lap_distance)).filter(distance => distance >= start && distance <= finish))].sort((a, b) => a - b);
      const points = distances.map(distance => ({distance, selected: batteryAt(selectedBattery, distance), comparison: batteryAt(comparisonBattery, distance)})).filter(point => point.selected != null && point.comparison != null);
      const fillSegment = (a, b, difference) => {
        if (!difference) return;
        ctx.fillStyle = difference > 0 ? "rgba(82,224,138,.26)" : "rgba(255,75,75,.24)";
        ctx.beginPath(); ctx.moveTo(xFor(a.distance), batteryYFor(a.selected));
        ctx.lineTo(xFor(b.distance), batteryYFor(b.selected)); ctx.lineTo(xFor(b.distance), batteryYFor(b.comparison));
        ctx.lineTo(xFor(a.distance), batteryYFor(a.comparison)); ctx.closePath(); ctx.fill();
      };
      for (let index = 1; index < points.length; index++) {
        const a = points[index - 1], b = points[index], aDifference = a.selected - a.comparison, bDifference = b.selected - b.comparison;
        if (aDifference * bDifference < 0) {
          const ratio = Math.abs(aDifference) / (Math.abs(aDifference) + Math.abs(bDifference));
          const crossing = {distance: a.distance + (b.distance - a.distance) * ratio,
            selected: a.selected + (b.selected - a.selected) * ratio,
            comparison: a.comparison + (b.comparison - a.comparison) * ratio};
          fillSegment(a, crossing, aDifference); fillSegment(crossing, b, bDifference);
        } else {
          fillSegment(a, b, aDifference || bDifference);
        }
      }
    };
    drawBatteryArea(selectedBattery);
    drawBatteryDifference();
    drawBatteryLine(comparisonBattery, true, .68);
    drawBatteryLine(selectedBattery);
    ctx.font = "11px system-ui, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    for (let value = 0; value <= 100; value += 25) {
      const y = batteryYFor(value); ctx.strokeStyle = "#8b7932"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(width - right, y); ctx.lineTo(width - right + 5, y); ctx.stroke();
      ctx.fillStyle = "#d8c15d"; ctx.fillText(`${value}%`, width - right + 8, y);
    }
    // Acceleration is intentionally drawn last so it remains the upper layer.
    drawMetricSeries(ctx, fastest, point => point.acceleration_g, xFor, yFor, COMPARISON_COLOR, true, .82);
    drawMetricSeries(ctx, selected, point => point.acceleration_g, xFor, yFor, SELECTED_COLOR);
    if (hoverDistance != null) {
      const values = [];
      for (const [points, owner] of [[selected, "Selected"], [fastest, "Comparison"]]) {
        const point = nearest(points, hoverDistance, "lap_distance");
        if (point) {
          values.push(`${owner}: ${Number(point.acceleration_g).toFixed(2)} G`);
          if (point.ers_percent != null && Number.isFinite(Number(point.ers_percent))) values.push(`${owner} battery: ${Math.round(Number(point.ers_percent))}%`);
        }
      }
      drawMetricHover(ctx, width, xFor(hoverDistance), top, height - bottom, values, 210);
    }
  });
}

function drawInputChart() {
  $("inputChart").style.height = innerWidth <= 700 ? "250px" : "270px";
  canvas("inputChart", (ctx, width, height) => {
    const selected = graphSamples(lap), fastest = graphSamples(reference);
    if (!selected.length) return;
    const all = [...selected, ...fastest], end = Math.max(...all.map(point => Number(point.lap_distance)), 1);
    const left = 52, right = 14, top = 15, bottom = TIME_AXIS_BOTTOM, graphHeight = height - top - bottom;
    const yFor = value => height - bottom - Number(value) / 100 * graphHeight;
    ctx.font = "11px system-ui, sans-serif"; ctx.textBaseline = "middle";
    for (let value = 0; value <= 100; value += 25) {
      const y = yFor(value); ctx.strokeStyle = value === 0 ? "#56636b" : "#293137"; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
      ctx.fillStyle = "#aeb9bf"; ctx.textAlign = "right"; ctx.fillText(`${value}%`, left - 6, y);
    }
    const xFor = drawDistanceGrid(ctx, width, height, end, left, right, top, bottom);
    drawSectionHighlight(ctx, xFor, top, height - bottom);
    for (const [points, dashed, alpha] of [[fastest, true, .48], [selected, false, 1]]) {
      drawMetricSeries(ctx, points, point => inputPercent(point, "throttle"), xFor, yFor, "#72ff28", dashed, alpha);
      drawMetricSeries(ctx, points, point => inputPercent(point, "brake"), xFor, yFor, "#ff4b4b", dashed, alpha);
    }
    if (hoverDistance != null) {
      const values = [];
      for (const [points, owner] of [[selected, "Selected"], [fastest, "Comparison"]]) {
        const point = nearest(points, hoverDistance, "lap_distance");
        if (point) values.push(`${owner}: T ${Math.round(inputPercent(point, "throttle"))}%  B ${Math.round(inputPercent(point, "brake"))}%`);
      }
      drawMetricHover(ctx, width, xFor(hoverDistance), top, height - bottom, values, 196);
    }
  });
}

function drawTrackMap() {
  $("trackMap").style.height = innerWidth <= 700 ? "280px" : "300px";
  canvas("trackMap", (ctx, width, height) => {
    const selected = graphSamples(lap).filter(x => x.position?.x != null && x.position?.z != null);
    const compared = graphSamples(reference).filter(x => x.position?.x != null && x.position?.z != null);
    const base = selected;
    const all = [...selected, ...compared]; if (!selected.length) return;
    const meanX = all.reduce((sum, sample) => sum + sample.position.x, 0) / all.length;
    const meanZ = all.reduce((sum, sample) => sum + sample.position.z, 0) / all.length;
    const covariance = all.reduce((value, sample) => {
      const x = sample.position.x - meanX, z = sample.position.z - meanZ;
      value.xx += x * x; value.zz += z * z; value.xz += x * z; return value;
    }, {xx: 0, zz: 0, xz: 0});
    const angle = .5 * Math.atan2(2 * covariance.xz, covariance.xx - covariance.zz);
    const cos = Math.cos(angle), sin = Math.sin(angle);
    const rotate = sample => {
      const x = sample.position.x - meanX, z = sample.position.z - meanZ;
      return [x * cos + z * sin, -x * sin + z * cos];
    };
    const rotated = all.map(rotate), xs = rotated.map(point => point[0]), zs = rotated.map(point => point[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minZ = Math.min(...zs), maxZ = Math.max(...zs);
    const scale = Math.min((width - 56) / (maxX - minX || 1), (height - 50) / (maxZ - minZ || 1));
    const ox = (width - (maxX - minX) * scale) / 2, oy = (height - (maxZ - minZ) * scale) / 2;
    const xy = sample => { const [x, z] = rotate(sample); return [ox + (x - minX) * scale, oy + (z - minZ) * scale]; };
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.strokeStyle = "#252c31"; ctx.lineWidth = 22; ctx.beginPath();
    base.forEach((sample, index) => { const [x, y] = xy(sample); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.stroke(); ctx.strokeStyle = "#4b555c"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.strokeStyle = COMPARISON_COLOR; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.beginPath();
    compared.forEach((sample, index) => { const [x, y] = xy(sample); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.stroke(); ctx.setLineDash([]);
    ctx.lineWidth = 3; ctx.strokeStyle = SELECTED_COLOR;
    for (let i = 1; i < selected.length; i++) {
      const a = selected[i - 1], b = selected[i], [ax, ay] = xy(a), [bx, by] = xy(b);
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    }
    trackHitPoints = selected.map(sample => { const [x, y] = xy(sample); return {x, y, distance: Number(sample.lap_distance)}; });
    if (selectedSection) {
      ctx.strokeStyle = "#ff6b72"; ctx.lineWidth = 10;
      for (let i = 1; i < selected.length; i++) {
        const a = selected[i - 1], b = selected[i];
        if (Number(b.lap_distance) < selectedSection.start_distance || Number(a.lap_distance) > selectedSection.end_distance) continue;
        const [ax, ay] = xy(a), [bx, by] = xy(b); ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
      }
    }
    const seasonPack = isSeasonPack(lap);
    const drawUsageRibbon = (isActive, color, offset) => {
      ctx.strokeStyle = color; ctx.lineWidth = 4;
      for (let index = 1; index < selected.length; index++) {
        const a = selected[index - 1], b = selected[index];
        if (!isActive(a) && !isActive(b)) continue;
        const [ax, ay] = xy(a), [bx, by] = xy(b), length = Math.hypot(bx - ax, by - ay) || 1;
        const nx = -(by - ay) / length, ny = (bx - ax) / length;
        ctx.beginPath(); ctx.moveTo(ax + nx * offset, ay + ny * offset);
        ctx.lineTo(bx + nx * offset, by + ny * offset); ctx.stroke();
      }
    };
    const aeroActive = sample => seasonPack ? Boolean(sample.active_aero) : Number(sample.drs) > 0;
    const boostActive = sample => seasonPack ? Number(sample.boost_active) > 0 && Number(sample.overtake_active) === 0 : Boolean(sample.ers_usage);
    const overtakeActive = sample => seasonPack && Number(sample.overtake_active) > 0;
    drawUsageRibbon(aeroActive, seasonPack ? "#ff4b8c" : "#52e08a", -7);
    drawUsageRibbon(boostActive, "#ffd84d", 7);
    if (seasonPack) drawUsageRibbon(overtakeActive, "#35a7ff", 7);
    const markerPosition = (distance, offset = 0) => {
      const index = selected.reduce((closest, sample, candidate) =>
        Math.abs(Number(sample.lap_distance) - Number(distance)) < Math.abs(Number(selected[closest].lap_distance) - Number(distance)) ? candidate : closest, 0);
      const before = selected[Math.max(0, index - 1)], after = selected[Math.min(selected.length - 1, index + 1)];
      const [x, y] = xy(selected[index]), [bx, by] = xy(before), [ax, ay] = xy(after);
      const length = Math.hypot(ax - bx, ay - by) || 1, nx = -(ay - by) / length, ny = (ax - bx) / length;
      return [x + nx * offset, y + ny * offset];
    };
    for (const event of analysis.events || []) {
      if (event.type === "active_aero" || event.type === "drs") continue;
      if (chartZoom && (event.start_distance < chartZoom.start || event.start_distance > chartZoom.end)) continue;
      const drivingEvent = event.type === "wheel_spin" || event.type === "tyre_lock";
      const [x, y] = markerPosition(event.start_distance);
      if (event.type === "lap_invalidated") {
        const flagWidth = 22, flagHeight = 12, left = x - flagWidth / 2, top = y - flagHeight / 2;
        ctx.fillStyle = "#fff"; ctx.fillRect(left, top, flagWidth, flagHeight);
        ctx.fillStyle = "#111"; ctx.beginPath(); ctx.moveTo(left, top); ctx.lineTo(left + flagWidth, top); ctx.lineTo(left, top + flagHeight); ctx.closePath(); ctx.fill();
        ctx.strokeStyle = "#d8e0e4"; ctx.lineWidth = 1.5; ctx.strokeRect(left, top, flagWidth, flagHeight);
      } else if (event.type === "pit_lane") {
        ctx.fillStyle = "#ec5cff"; ctx.strokeStyle = "#160719"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.fillStyle = "#fff"; ctx.font = "bold 11px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("P", x, y + .5);
      } else if (drivingEvent) {
        ctx.fillStyle = event.type === "wheel_spin" ? "#ff3b45" : "#ff8a36";
        ctx.strokeStyle = "#080b0e"; ctx.lineWidth = 3;
        ctx.beginPath();
        if (event.type === "wheel_spin") ctx.arc(x, y, 6, 0, Math.PI * 2);
        else { ctx.moveTo(x, y - 7); ctx.lineTo(x + 7, y); ctx.lineTo(x, y + 7); ctx.lineTo(x - 7, y); ctx.closePath(); }
        ctx.fill(); ctx.stroke();
      }
    }
    if (!chartZoom || chartZoom.start === 0) {
    const start = selected.reduce((first, sample) => sample.lap_distance < first.lap_distance ? sample : first);
    const [startX, startY] = xy(start), cell = 4, columns = 5, rows = 4;
    const flagLeft = startX - columns * cell / 2, flagTop = startY - rows * cell / 2;
    for (let row = 0; row < rows; row++) {
      for (let column = 0; column < columns; column++) {
        ctx.fillStyle = (row + column) % 2 ? "#fff" : "#111";
        ctx.fillRect(flagLeft + column * cell, flagTop + row * cell, cell, cell);
      }
    }
    ctx.strokeStyle = "#d8e0e4"; ctx.lineWidth = 1.5;
    ctx.strokeRect(flagLeft, flagTop, columns * cell, rows * cell);
    }
    if (hoverDistance != null) {
      const sample = nearest(selected, hoverDistance, "lap_distance"), [x, y] = xy(sample);
      ctx.fillStyle = "#fff"; ctx.strokeStyle = "#080b0e"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
  });
}

function plot() { drawSpeedChart(); drawTrackMap(); drawAccelerationChart(); drawInputChart(); }

function renderTimeLosses() {
  renderLossInsights();
  if (!$('losses')) return;
  if (!reference) {
    $("losses").innerHTML = "<div>Select a different comparison lap to summarize pace by section</div>";
    return;
  }
  const zones = comparisonAnalysis?.pace_zones || [];
  const selectedName = `Lap ${lap.lapNumber}`, comparisonName = `Lap ${reference.lapNumber}`;
  const selectedCount = zones.filter(zone => zone.faster === "selected").length;
  const comparisonCount = zones.filter(zone => zone.faster === "comparison").length;
  const summary = `<div class="pace-summary"><span><b style="color:${SELECTED_COLOR}">${selectedName}</b> faster: ${selectedCount} zones</span><span><b style="color:${COMPARISON_COLOR}">${comparisonName}</b> faster: ${comparisonCount} zones</span><span>Showing differences ≥ 50 ms</span></div>`;
  const rows = zones.map(zone => {
    const selectedFaster = zone.faster === "selected";
    const fasterName = selectedFaster ? selectedName : comparisonName;
    const signedDifference = signedTime((selectedFaster ? -1 : 1) * Number(zone.time_difference_ms));
    return `<div class="pace-zone ${selectedFaster ? "selected-faster" : "comparison-faster"}"><strong>${fasterName} faster</strong><span>${Math.round(zone.start_distance)}–${Math.round(zone.end_distance)} m</span><b>${signedDifference}</b></div>`;
  }).join("");
  $("losses").innerHTML = zones.length ? summary + rows : "<div>No meaningful pace difference detected between these laps</div>";
}

function renderLossInsights() {
  const root = $("lossInsights");
  if (!root) return;
  selectedSection = null;
  if (!reference) {
    root.innerHTML = `<p class="insight-muted">${comparisonLapId && comparisonLapId !== selectedLapId ? 'Comparison unavailable. Select the lap again to retry.' : 'Select a different comparison lap to see where time was lost.'}</p>`;
    return;
  }
  if (!comparisonAnalysis) {
    root.innerHTML = '<p class="insight-muted">Comparison analysis is unavailable. Select the lap again to retry.</p>';
    return;
  }
  const context = comparisonAnalysis.comparison_context || {};
  const gaps = comparisonAnalysis.recording_gaps || [];
  const losses = (comparisonAnalysis.losses || []).slice(0, 3);
  const labels = {EARLY_BRAKING: 'Braking began earlier', LATE_THROTTLE: 'Throttle applied later', LOW_MINIMUM_SPEED: 'Lower minimum speed', WHEEL_SPIN: 'Wheel spin detected', TYRE_LOCK: 'Tyre lock detected', LAP_INVALIDATED: 'Lap invalidated', LARGE_TIME_LOSS: 'Time difference observed; cause unclear'};
  root.innerHTML = `<div class="insight-context"><strong>${escapeHtml(context.label || 'Conditions unknown')}</strong><p>${escapeHtml((context.notes || []).join(' · ') || 'Compound, setup, starting fuel, wear and ERS are similar.')}</p></div>` +
    (gaps.length ? `<details class="insight-gaps"><summary>${gaps.length} recording gap(s): affected areas excluded from coaching</summary>${gaps.map(g => `<div>${Math.round(g.start_distance)}–${Math.round(g.end_distance)} m</div>`).join('')}</details>` : '') +
    `<div class="insight-grid">${losses.map((loss, index) => {
      const evidence = (loss.reasons || []).map(reason => `${labels[reason.type] || reason.type}${reason.distance_difference_m != null ? ` (${reason.distance_difference_m} m)` : ''}`).join(' · ');
      return `<button type="button" class="insight-card" data-loss="${index}" aria-pressed="false"><span>${Math.round(loss.start_distance)}–${Math.round(loss.end_distance)} m</span><strong>+${(loss.time_loss_ms / 1000).toFixed(3)} s</strong><p>${escapeHtml(evidence)}</p><small>${context.notes?.length ? 'Limited evidence · conditions differ or are unknown' : 'Rule-based evidence · association, not a proven cause'}</small><span class="insight-action">Highlight on charts and map →</span></button>`;
    }).join('')}</div>` + (losses.length ? '' : '<p class="insight-muted">No supported time-loss area ≥ 50 ms found in the available data.</p>');
  root.querySelectorAll('[data-loss]').forEach(button => button.addEventListener('click', () => {
    zoomToSection(losses[Number(button.dataset.loss)]);
    root.querySelectorAll('[data-loss]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    $("speedChart").scrollIntoView({behavior: 'smooth', block: 'center'});
  }));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[character]));
}

function analysisTarget() {
  const session = $("sessionSelect").value, trackId = lap?.trackId;
  return session && trackId != null ? {session, trackId} : null;
}

function selectAnalysisSection(section) {
  selectedSection = section;
  $("sectionSelectionLabel").textContent = section ? `${section.name} selected · all charts linked` : "Select a row to highlight all graphs";
  document.querySelectorAll(".section-row[data-index]").forEach(row => row.classList.toggle("selected", Number(row.dataset.index) === section?.index));
  if (section) hoverDistance = (Number(section.start_distance) + Number(section.end_distance)) / 2;
  plot();
}

function selectSectionAtDistance(distance) {
  if (!sessionAnalysis?.sections?.length || distance == null) return;
  const section = sessionAnalysis.sections.find(row => Number(row.start_distance) <= distance && distance < Number(row.end_distance));
  if (section) selectAnalysisSection(section);
}

function renderSessionAnalysis(result) {
  sessionAnalysis = result; selectedSection = null;
  $("reanalyzeSession").hidden = false;
  $("analysisUnavailable").hidden = true;
  if (!result.analyzable) {
    $("sessionAnalysisSummary").hidden = true; $("sessionSections").hidden = true; $("losses").hidden = true;
    $("analysisUnavailable").hidden = false;
    $("analysisUnavailable").textContent = `分析不能: ${result.reason || "十分な比較データがありません"}（記録 ${result.sample_counts?.recorded_laps || 0} 周）`;
    return;
  }
  $("sessionAnalysisSummary").hidden = false; $("sessionSections").hidden = false; $("losses").hidden = true;
  $("theoreticalFastest").textContent = time(result.theoretical_fastest_ms);
  $("estimatedLoss").textContent = `+${(Number(result.selected_estimated_loss_ms) / 1000).toFixed(3)} s`;
  const wear = result.tyre_wear_estimate || {};
  $("wearLoss").textContent = wear.estimated_loss_ms == null ? "分析不能" : `+${(Number(wear.estimated_loss_ms) / 1000).toFixed(3)} s`;
  const events = result.event_loss_estimates || {};
  $("eventLoss").textContent = `+${((Number(events.wheel_spin) + Number(events.tyre_lock)) / 1000).toFixed(3)} s`;
  const counts = result.sample_counts || {}, confidence = result.confidence || {};
  $("analysisConfidence").textContent = `${confidence.label || "—"} ${(Number(confidence.score || 0) * 100).toFixed(0)}% · ${counts.eligible_laps || 0} laps`;
  const topIndexes = new Set((result.top_improvement_sections || []).map(section => Number(section.index)));
  const effectSummary = `<div class="section-effects"><span>Comparison: Lap ${escapeHtml(result.comparison_lap_number)} (${escapeHtml(result.comparison_reason)})</span><span>ERS faster: ${(result.ers_faster_sections || []).length} sections</span><span>ERS save candidates: ${(result.ers_save_candidate_sections || []).length}</span><span>Active Aero/DRS differences: ${(result.active_aero_differences || []).length}</span></div>`;
  const header = `<div class="section-row header"><span>Section</span><span>Delta</span><span>Likely cause</span><span>Improvement</span><span>Confidence</span></div>`;
  const rows = (result.sections || []).map(section => `<div class="section-row ${topIndexes.has(Number(section.index)) ? "loss-major" : ""}" data-index="${Number(section.index)}"><b>${escapeHtml(section.name)}</b><span class="delta" style="color:${Number(section.segment_delta_ms) > 0 ? "#ff7b81" : "#52e08a"}">${signedTime(section.segment_delta_ms)}</span><span class="cause">${escapeHtml(section.primary_cause)}</span><span class="suggestion">${escapeHtml(section.suggestion)} · Best Lap ${escapeHtml(section.best_lap_number)}</span><span class="confidence">${escapeHtml(section.confidence?.label)} ${(Number(section.confidence?.score || 0) * 100).toFixed(0)}%<br>${section.sample_count} laps</span></div>`).join("");
  $("sessionSections").innerHTML = effectSummary + header + rows;
  $("sessionSections").querySelectorAll(".section-row[data-index]").forEach(row => row.onclick = () => selectAnalysisSection(result.sections.find(section => Number(section.index) === Number(row.dataset.index))));
}

function showAnalysisStatus(status) {
  const active = status.state === "queued" || status.state === "running";
  $("analyzeSession").disabled = active; $("reanalyzeSession").disabled = active;
  $("analysisProgress").hidden = !active;
  $("analysisProgressBar").value = Number(status.progress) || 0;
  $("analysisProgressLabel").textContent = `${Number(status.progress) || 0}% · ${status.current || ""}`;
  $("analysisError").hidden = status.state !== "failed";
  $("analysisError").textContent = status.error ? `分析失敗: ${status.error}` : "";
  $("sessionAnalysisText").textContent = status.state === "completed" ? "保存済みの分析結果を表示しています。" : status.current || "保存済みテレメトリーを分析します。";
}

async function fetchAnalysisStatus(startPolling = false) {
  const target = analysisTarget(); if (!target) return;
  if (analysisPollTimer) { clearTimeout(analysisPollTimer); analysisPollTimer = null; }
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(target.session)}/analysis/status?track_id=${encodeURIComponent(target.trackId)}`, {cache: "no-store"});
    const status = await response.json(); if (!response.ok) throw Error(status.error || "Could not read analysis status");
    showAnalysisStatus(status);
    if (status.state === "completed") {
      const resultResponse = await fetch(`/api/sessions/${encodeURIComponent(target.session)}/analysis/result?track_id=${encodeURIComponent(target.trackId)}`, {cache: "no-store"});
      if (resultResponse.ok) renderSessionAnalysis(await resultResponse.json());
    } else if (status.state === "queued" || status.state === "running" || startPolling) {
      analysisPollTimer = setTimeout(() => fetchAnalysisStatus(true), 800);
    } else if (!status.state) {
      $("reanalyzeSession").hidden = true;
    }
  } catch (error) { showAnalysisStatus({state: "failed", progress: 0, error: error.message}); }
}

async function startSessionAnalysis(force = false) {
  const target = analysisTarget(); if (!target) return;
  $("analysisError").hidden = true;
  const response = await fetch(`/api/sessions/${encodeURIComponent(target.session)}/analysis`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({track_id: target.trackId, selected_lap_id: selectedLapId, force}),
  });
  const status = await response.json();
  if (!response.ok) { showAnalysisStatus({state: "failed", progress: 0, error: status.error || "Could not start analysis"}); return; }
  showAnalysisStatus(status); fetchAnalysisStatus(true);
}

async function load(id) {
  const version = ++lapLoadVersion;
  selectedLapId = id;
  const [a, b] = await Promise.all([fetch(`/api/laps/${id}`), fetch(`/api/laps/${id}/analysis`)]);
  const [loadedLap, loadedAnalysis] = await Promise.all([a.json(), b.json()]);
  if (version !== lapLoadVersion) return;
  if (!a.ok || !b.ok) {$("message").textContent = loadedLap.error || loadedAnalysis.error || 'Could not load lap.'; return;}
  lap = loadedLap; analysis = loadedAnalysis; hoverDistance = null; chartZoom = null;
  SessionContext.write($("sessionSelect").value, lap.trackId);
  selectedLapId = id; renderLapList();
  await setComparison(comparisonLapId, false);
  if (version !== lapLoadVersion) return;
  $("gameVersion").textContent = gameVersionLabel(lap);
  let udpWarning = $("udpConfigurationWarning");
  if (!udpWarning) {
    udpWarning = document.createElement("p"); udpWarning.id = "udpConfigurationWarning";
    udpWarning.style.cssText = "max-width:720px;margin:8px 0;padding:8px 10px;border:1px solid #8c7230;border-radius:7px;background:#241e10;color:#ffd84d;font-size:.76rem";
    $("gameVersion").after(udpWarning);
  }
  udpWarning.hidden = !lap.udpConfigurationWarning;
  udpWarning.textContent = lap.udpConfigurationWarning || "";
  const aeroUsageLabel = $("aeroUsageLabel");
  aeroUsageLabel.textContent = isSeasonPack(lap) ? "Active Aero" : "DRS";
  aeroUsageLabel.className = `usage-key ${isSeasonPack(lap) ? "active-aero" : "drs"}`;
  const mapAeroLabel = $("mapAeroLabel");
  mapAeroLabel.textContent = isSeasonPack(lap) ? "Active Aero" : "DRS";
  mapAeroLabel.className = isSeasonPack(lap) ? "active-aero-marker" : "drs-marker";
  $("mapOvertakeLabel").hidden = !isSeasonPack(lap);
  $("boostUsageLabel").textContent = "ERS";
  $("overtakeUsageLabel").textContent = "ERS";
  $("overtakeUsageLabel").hidden = !isSeasonPack(lap);
  $("lapTime").textContent = time(lap.lapTimeMs);
  $("tyreCompound").textContent = tyreSummary(lap) || "—";
  $("lapNote").value = lap.note || ""; $("noteStatus").textContent = "";
  const previous = analysis.summary?.vs_previous_ms;
  $("previousDelta").textContent = previous == null ? "—" : signedTime(previous);
  $("previousDelta").style.color = analysis.summary?.is_session_best ? "#c16cff" : previous < 0 ? "#52e08a" : "#ffd84d";
  renderTyreWear();
  window.AnalysisWorkspace?.load(id, lap);
  plot();
}

function sessionLabel(session, items) {
  const stamp = session.replace("_session-", " · ").replace("_", " ");
  const tracks = [...new Set(items.map(item => item.trackName || `Track ${item.trackId}`))].join(", ");
  return `${stamp} · ${tracks}`;
}

function renderLapList() {
  const session = $("sessionSelect").value;
  const items = lapsCache.filter(item => (item.session || "Legacy session") === session);
  const valid = items.filter(item => item.validLap && Number(item.lapTimeMs) > 0);
  const best = valid.reduce((fastest, item) => !fastest || item.lapTimeMs < fastest.lapTimeMs ? item : fastest, null);
  const bestTyre = best?.tyreCompound || "Tyre unknown";
  const bestAge = best?.tyreAgeLapsAtStart == null ? "" : ` · ${best.tyreAgeLapsAtStart} lap`;
  $("fastestLap").innerHTML = best ? `<span>Lap ${best.lapNumber} <em>(FASTEST LAP)</em><small>${bestTyre}${bestAge}</small></span><strong>${time(best.lapTimeMs)}</strong>` : `<span>No valid lap</span>`;
  const option = item => {
    const tyre = item.tyreCompound || "Tyre unknown";
    const age = item.tyreAgeLapsAtStart == null ? "" : ` · ${item.tyreAgeLapsAtStart} lap`;
    const pit = item.pitLaneUsed ? " · PIT" : "";
    const current = item.id === selectedLapId, fastest = item.id === best?.id;
    const highlight = fastest ? "session-best-option" : current ? "current-lap-option" : "";
    const marker = `${fastest ? " · FASTEST LAP" : ""}${current ? " · SELECTED" : ""}`;
    return `<option class="${highlight}" value="${item.id}">Lap ${item.lapNumber}${marker}  ·  ${tyre}${age}${pit}  ·  ${time(item.lapTimeMs)}  ·  ${item.validLap ? "VALID" : "INVALID"}</option>`;
  };
  $("lapSelect").innerHTML = items.map(option).join("");
  if (items.some(item => item.id === selectedLapId)) $("lapSelect").value = selectedLapId;
  const candidates = items;
  let comparison = candidates.find(item => item.id === comparisonLapId);
  if (!comparison) comparison = candidates.find(item => item.id === selectedLapId) || candidates[0];
  comparisonLapId = comparison?.id || null;
  $("compareLapSelect").innerHTML = candidates.map(option).join("") || `<option value="">No other lap</option>`;
  $("compareLapSelect").disabled = !comparison;
  if (comparison) $("compareLapSelect").value = comparison.id;
}

async function setComparison(id, redraw = true) {
  comparisonLapId = id || null; reference = null; comparisonAnalysis = null;
  selectedSection = null; chartZoom = null;
  const requestedLap = selectedLapId, requestedComparison = comparisonLapId;
  if ($("lossInsights")) $("lossInsights").innerHTML = '<p class="insight-muted">Loading comparison…</p>';
  if (comparisonLapId && comparisonLapId !== selectedLapId) {
    try {
    const [lapResponse, analysisResponse] = await Promise.all([
      fetch(`/api/laps/${comparisonLapId}`),
      fetch(`/api/laps/${selectedLapId}/analysis?reference_id=${encodeURIComponent(comparisonLapId)}`),
    ]);
    const loadedReference = lapResponse.ok ? await lapResponse.json() : null;
    const loadedAnalysis = analysisResponse.ok ? await analysisResponse.json() : null;
    if (selectedLapId !== requestedLap || comparisonLapId !== requestedComparison) return;
    reference = loadedReference;
    comparisonAnalysis = loadedAnalysis;
    } catch (error) {
      if (selectedLapId !== requestedLap || comparisonLapId !== requestedComparison) return;
      $("message").textContent = 'Could not load comparison. Select the lap again to retry.';
    }
  }
  const comparing = Boolean(reference);
  $("speedComparisonKey").hidden = !comparing;
  $("accelerationComparisonKey").hidden = !comparing;
  $("batteryHigherKey").hidden = !comparing;
  $("batteryLowerKey").hidden = !comparing;
  $("inputComparisonKey").hidden = !comparing;
  $("comparedTyre").textContent = reference ? tyreSummary(reference) : "";
  updateComparisonSummary();
  renderTimeLosses();
  zoomToSection(null);
  window.AnalysisWorkspace?.compare(selectedLapId, comparisonLapId);
  if (redraw && lap) plot();
}

function renderTyreWear() {
  const wheels = [["front_left", "FL"], ["front_right", "FR"], ["rear_left", "RL"], ["rear_right", "RR"]];
  const rawValues = wheels.flatMap(([key]) => [lap.tyreWearAtStart?.[key], lap.tyreWearAtEnd?.[key]]);
  const values = rawValues.filter(value => value != null).map(Number).filter(Number.isFinite);
  const legacyMisread = values.length === 8 && values.every(value => Math.abs(value) < .01) && values.some(value => value > 0 && value < .0001);
  if (values.length !== 8 || legacyMisread) {
    $("wear").innerHTML = `<div class="wear-unavailable">Tyre wear unavailable for this recorded lap</div>`;
    return;
  }
  $("wear").innerHTML = wheels.map(([key, label]) => {
    const start = Math.max(0, Math.min(100, Number(lap.tyreWearAtStart[key])));
    const end = Math.max(start, Math.min(100, Number(lap.tyreWearAtEnd[key])));
    const change = Math.max(0, end - start);
    return `<div class="wear-wheel"><span>${label}</span><div class="wear-donut" style="--prior:${start.toFixed(1)}%;--total:${end.toFixed(1)}%"><strong>${end.toFixed(0)}%</strong></div><small>Before ${start.toFixed(1)}%<br>This lap +${change.toFixed(1)}%</small></div>`;
  }).join("");
}

let lapRefreshBusy = false, lapListFingerprint = '', hoverFrame = null;
function schedulePlot() {
  if (hoverFrame !== null) return;
  hoverFrame = requestAnimationFrame(() => { hoverFrame = null; if (lap) plot(); });
}
async function refreshLaps(initial = false) {
  // Recording runs independently in the backend. Background windows do not
  // need to rebuild controls; refresh promptly when the user returns.
  if (lapRefreshBusy || (!initial && document.hidden)) return;
  lapRefreshBusy = true;
  try {
    const response = await fetch("/api/laps", {cache: "no-store"});
    if (!response.ok) throw Error("Could not refresh laps");
    const laps = await response.json(); if (!laps.length) throw Error("Waiting for a completed lap...");
    const fingerprint = JSON.stringify(laps);
    if (!initial && lap && fingerprint === lapListFingerprint) {
      const status = window.F1_DESKTOP_MODE === 'test'
        ? "Test copy of real previous laps · recording disabled"
        : "Live: checking for completed laps every 3 seconds";
      const translated = window.I18n?.t(status) || status;
      if ($("message").textContent !== translated) $("message").textContent = status;
      return;
    }
    const previousSession = $("sessionSelect").value, newest = laps[0], isNew = newest.id !== knownLatest;
    lapsCache = laps;
    const groups = laps.reduce((all, item) => { const key = item.session || "Legacy session"; (all[key] ??= []).push(item); return all; }, {});
    $("sessionSelect").innerHTML = Object.entries(groups).map(([session, items]) => `<option value="${session}">${sessionLabel(session, items)}</option>`).join("");
    const savedSession = SessionContext.read().session_id;
    const preferredSession = groups[previousSession] ? previousSession : groups[savedSession] ? savedSession : null;
    const session = preferredSession || newest.session || "Legacy session";
    $("sessionSelect").value = session; renderLapList();
    const contextLap = groups[session]?.[0]; SessionContext.write(session, contextLap?.trackId);
    let target = selectedLapId && laps.find(item => item.id === selectedLapId && (item.session || "Legacy session") === session)?.id;
    if (!target) target = groups[session][0].id;
    if (initial || isNew || !lap) {
      const loadId = isNew && (newest.session || "Legacy session") === session ? newest.id : target;
      if (initial || isNew) comparisonLapId = loadId;
      await load(loadId);
    }
    knownLatest = newest.id;
    lapListFingerprint = fingerprint;
    $("message").textContent = window.F1_DESKTOP_MODE === 'test'
      ? "Test copy of real previous laps · recording disabled"
      : "Live: checking for completed laps every 3 seconds";
  } catch (error) { $("message").textContent = error.message; }
  finally { lapRefreshBusy = false; }
}

async function init() {
  $("resetZoom").onclick = () => zoomToSection(null);
  SessionContext.mount($("sessionSelect"), null);
  $("lapSelect").onchange = event => { comparisonLapId = event.target.value; load(event.target.value); };
  $("compareLapSelect").onchange = event => setComparison(event.target.value);
  $("sessionSelect").onchange = () => {
    selectedLapId = null; comparisonLapId = null; reference = null; sessionAnalysis = null; selectedSection = null;
    renderLapList();
    const first = lapsCache.find(item => (item.session || "Legacy session") === $("sessionSelect").value);
    if (first) { SessionContext.write($("sessionSelect").value, first.trackId); load(first.id); }
  };
  $("saveNote").onclick = async () => {
    const button = $("saveNote"), note = $("lapNote").value, id = selectedLapId;
    button.disabled = true; $("noteStatus").textContent = "Saving...";
    try {
      const response = await fetch(`/api/laps/${id}/note`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({note})});
      const result = await response.json(); if (!response.ok) throw Error(result.error || "Could not save note");
      lap.note = result.note; $("noteStatus").textContent = "Saved";
    } catch (error) { $("noteStatus").textContent = error.message; }
    finally { button.disabled = false; }
  };
  const bindDistanceHover = (id, left = TIME_AXIS_LEFT, right = TIME_AXIS_RIGHT) => {
    $(id).addEventListener("mousemove", event => {
      const samples = graphSamples(lap); if (!samples.length) return;
      const rect = event.currentTarget.getBoundingClientRect(), end = Math.max(...samples.map(sample => Number(sample.lap_distance)), 1);
      const graphWidth = rect.width - left - right;
      const range = distanceRange(end);
      hoverDistance = range.start + Math.max(0, Math.min(1, (event.clientX - rect.left - left) / graphWidth)) * (range.end - range.start); schedulePlot();
    });
    $(id).addEventListener("mouseleave", () => { hoverDistance = null; schedulePlot(); });
  };
  bindDistanceHover("speedChart");
  bindDistanceHover("accelerationChart", 62, 52);
  bindDistanceHover("inputChart", 52, 14);
  for (const id of ["speedChart", "accelerationChart", "inputChart"]) $(id).addEventListener("click", () => selectSectionAtDistance(hoverDistance));
  $("trackMap").addEventListener("click", event => {
    if (!trackHitPoints.length) return;
    const rect = event.currentTarget.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top;
    const nearestPoint = trackHitPoints.reduce((best, point) => Math.hypot(point.x - x, point.y - y) < Math.hypot(best.x - x, best.y - y) ? point : best);
    selectSectionAtDistance(nearestPoint.distance);
  });
  await refreshLaps(true); setInterval(() => refreshLaps(false), 3000);
}
init(); addEventListener("resize", schedulePlot);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshLaps(false); });
