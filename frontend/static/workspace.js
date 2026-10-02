(function () {
  const get = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const metric = (v, unit = '', digits = 1) => v == null ? '—' : `${Number(v).toFixed(digits)}${unit}`;
  const time = v => v == null ? '—' : `${Math.floor(v / 60000)}:${((v % 60000) / 1000).toFixed(3).padStart(6, '0')}`;
  let currentId = null, data = null, stintIndex = 0, comparisonToken = 0;
  const root = get('workspacePanels');
  root.innerHTML = `<details class="card" id="consistencyPanel" open><summary>Corner consistency <small id="consistencyCount"></small></summary><p id="consistencyMethod" class="workspace-muted"></p><div id="consistencyRows"></div></details>
    <details class="card" id="stintPanel" open><summary>Stint dashboard</summary><div class="workspace-controls"><label>Stint <select id="stintSelect"></select></label><label><input id="includeUnclean" type="checkbox"> Include pit and invalid laps</label></div><p id="stintNotice" class="workspace-muted"></p><div id="stintStats" class="workspace-stats"></div><div id="stintCharts" class="stint-charts"></div><div id="stintTable" class="workspace-table"></div></details>
    <details class="card" id="wearPanel"><summary>Tyre wear and pace evidence</summary><p id="wearEvidence"></p><p id="wearMethod" class="workspace-muted"></p></details>
    <details class="card" id="setupPanel"><summary>Setup comparison <small id="setupCount"></small></summary><div id="setupRows">Select a different comparison lap.</div></details>`;
  const health = document.createElement('details'); health.className = 'recording-health';
  health.innerHTML = '<summary id="recordingStatus">Checking recording…</summary><div id="recordingGroups"></div><small id="recordingNotice"></small>';
  document.querySelector('header').append(health);
  get('stintSelect').onchange = event => {stintIndex = Number(event.target.value); renderStint();};
  get('includeUnclean').onchange = renderStint;
  get('stintPanel').addEventListener('toggle', () => {if (get('stintPanel').open) renderStint();});
  document.querySelectorAll('.lap-note').forEach(article => {
    const detail = document.createElement('details'); detail.className = 'card note-disclosure';
    const summary = document.createElement('summary'); summary.textContent = 'Lap note';
    article.before(detail); detail.append(summary, article); article.classList.remove('card'); article.querySelector('h2')?.remove();
  });

  async function json(url) {
    const response = await fetch(url, {cache:'no-store'});
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || 'Request failed');
    return value;
  }
  async function pollHealth() {
    if (window.F1_DESKTOP_MODE === 'test') {
      get('recordingStatus').textContent = 'Recording off · Test laps';
      get('recordingNotice').textContent = 'This window uses a separate test copy and does not listen for game telemetry.';
      return;
    }
    try {
      const health = await json('/api/recording-health');
      const savingFailed = health.saving?.ok === false;
      get('recordingStatus').textContent = savingFailed ? 'Recording: save error' : `Recording: ${health.state}`;
      get('recordingStatus').dataset.state = savingFailed ? 'save-error' : health.state;
      get('recordingGroups').innerHTML = health.groups.map(group => `<div><span>${esc(group.name)}</span><b data-state="${group.state}">${group.state}${group.age_s != null ? ` · ${group.age_s.toFixed(1)} s ago` : ''}</b></div>`).join('');
      get('recordingNotice').textContent = savingFailed
        ? 'Some lap saves failed. Check free disk space and folder permissions, then open the logs folder for details.'
        : health.notice;
    } catch { get('recordingStatus').textContent = 'Recording status unavailable'; }
    setTimeout(pollHealth, 3000);
  }
  pollHealth();

  function renderConsistency(value) {
    get('consistencyCount').textContent = `${value.eligible_laps} comparable laps`;
    get('consistencyMethod').textContent = value.method;
    get('consistencyRows').innerHTML = value.reason ? `<p class="workspace-muted">${esc(value.reason)}</p>` :
      `<div class="workspace-table"><table><thead><tr><th>Corner</th><th>Laps</th><th>Time spread</th><th>Brake-point spread</th><th>Throttle-point spread</th><th>Minimum-speed spread</th><th>Slower than median</th></tr></thead><tbody>${value.rows.map((row, i) => `<tr><td><button data-corner="${i}">${esc(row.label)} · ${Math.round(row.start_distance)}–${Math.round(row.end_distance)} m</button></td><td>${row.lap_count}</td><td>${metric(row.time_range_ms / 1000,' s',3)}</td><td>${metric(row.brake_m_range,' m')}</td><td>${metric(row.throttle_m_range,' m')}</td><td>${metric(row.minimum_speed_kph_range,' km/h')}</td><td>${row.slower_than_median_count}/${row.lap_count}</td></tr>`).join('')}</tbody></table></div>`;
    get('consistencyRows').querySelectorAll('[data-corner]').forEach(button => button.onclick = () => {
      window.zoomAnalysisSection(value.rows[Number(button.dataset.corner)]);
      get('speedChart').scrollIntoView({behavior:'smooth',block:'center'});
    });
  }

  function sparkline(rows, field, title, unit, color, format = null) {
    const values = rows.filter(row => row[field] != null);
    if (!values.length) return `<article><h3>${title}</h3><p class="workspace-muted">No recorded data</p></article>`;
    const low = Math.min(...values.map(row => row[field])), high = Math.max(...values.map(row => row[field]));
    const spread = Math.max(high - low, 1);
    const x = i => 36 + i / Math.max(1, rows.length - 1) * 340;
    const y = v => 104 - (v - low) / spread * 76;
    let segments = [], line = [];
    rows.forEach((row, i) => {if (row[field] == null) {if (line.length) segments.push(line.join(' ')); line = [];} else line.push(`${x(i)},${y(row[field])}`);});
    if (line.length) segments.push(line.join(' '));
    const label = v => format ? format(v) : metric(v, unit);
    return `<article><h3>${title}</h3><svg viewBox="0 0 410 145" role="img" aria-label="${title} by recorded lap"><line x1="36" y1="106" x2="376" y2="106" stroke="#394249"/>${segments.map(points => `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2"/>`).join('')}${rows.map((row,i) => row[field] == null ? '' : `<circle cx="${x(i)}" cy="${y(row[field])}" r="3" fill="${color}"><title>Lap ${row.lap_number}: ${label(row[field])}</title></circle>`).join('')}<text x="36" y="18">${label(high)}</text><text x="36" y="124">${label(low)}</text><text x="235" y="140">${rows.length} recorded laps →</text></svg></article>`;
  }

  function renderStint() {
    const stint = data?.stints[stintIndex];
    if (!stint) return;
    const include = get('includeUnclean').checked;
    const rows = stint.laps.filter(row => include || row.eligible);
    const cleanTimes = rows.filter(row => row.eligible && row.time_ms != null).map(row => row.time_ms).sort((a,b) => a-b);
    const middle = Math.floor(cleanTimes.length / 2);
    const typical = cleanTimes.length ? (cleanTimes[middle] + cleanTimes[Math.floor((cleanTimes.length - 1) / 2)]) / 2 : null;
    get('stintNotice').textContent = `${stint.reason}. Stints are inferred from compound, tyre-age/wear resets and pit boundaries. Unknown tyre changes may be missed. Showing ${rows.length}/${stint.laps.length} laps.`;
    get('stintStats').innerHTML = `<span>Clean laps <b>${cleanTimes.length}</b></span><span>Typical clean pace <b>${time(typical)}</b></span><span>Best clean pace <b>${time(cleanTimes[0])}</b></span>`;
    get('stintCharts').innerHTML = rows.length ? sparkline(rows,'time_ms','Lap pace',' s','#40cfff',time) + sparkline(rows,'fuel_kg','Starting fuel',' kg','#6fe7bf') + sparkline(rows,'wear_percent','Starting tyre wear','%','#ff9f68') + sparkline(rows,'ers_percent','Starting ERS charge','%','#ffd84d') : '<p class="workspace-muted">No clean laps in this stint. Enable the filter above to inspect excluded laps.</p>';
    get('stintTable').innerHTML = `<table><thead><tr><th>Lap</th><th>Time</th><th>Fuel</th><th>Wear</th><th>ERS start → end</th><th>Status</th></tr></thead><tbody>${rows.map(row => `<tr><td>${row.lap_number}</td><td>${time(row.time_ms)}</td><td>${metric(row.fuel_kg,' kg')}</td><td>${metric(row.wear_percent,'%')}</td><td>${metric(row.ers_percent,'%')} → ${metric(row.ers_end_percent,'%')}</td><td>${row.pit ? 'Pit' : row.valid ? 'Clean' : 'Invalid'}</td></tr>`).join('')}</tbody></table>`;
  }

  window.AnalysisWorkspace = {
    async load(id) {
      currentId = id; data = null; get('consistencyRows').textContent = 'Loading session insights…';
      get('consistencyCount').textContent = ''; get('consistencyMethod').textContent = '';
      get('stintSelect').innerHTML = ''; get('stintNotice').textContent = '';
      get('wearEvidence').textContent = 'Loading wear evidence…'; get('wearMethod').textContent = '';
      get('stintCharts').textContent = 'Loading stint data…'; get('stintStats').textContent = ''; get('stintTable').textContent = '';
      try {
        const value = await json(`/api/laps/${id}/workspace-insights`);
        if (currentId !== id) return;
        data = value; stintIndex = Math.max(0, data.stints.findIndex(stint => stint.laps.some(row => row.id === id)));
        renderConsistency(data.consistency);
        get('stintSelect').innerHTML = data.stints.map((stint,i) => `<option value="${i}">Stint ${stint.number} · ${esc(stint.compound || 'Compound unknown')} · ${stint.laps.length} laps</option>`).join('');
        get('stintSelect').value = String(stintIndex); renderStint();
        const wear = value.tyre_wear_estimate;
        get('wearEvidence').textContent = wear.estimated_loss_ms == null ? wear.reason : `Estimated within-lap pace loss: +${(wear.estimated_loss_ms/1000).toFixed(3)} s. ${wear.reason}`;
        get('wearMethod').textContent = `${wear.method} · ${wear.sample_count} laps / ${wear.pair_count} pairs`;
      } catch (error) {
        if (currentId !== id) return;
        get('consistencyRows').textContent = error.message; get('stintCharts').textContent = 'Session insights unavailable.';
        get('wearEvidence').textContent = 'Wear evidence unavailable.';
      }
    },
    async compare(id, other) {
      const token = ++comparisonToken;
      get('setupCount').textContent = '';
      if (!id || !other || id === other) {get('setupRows').textContent = 'Select a different comparison lap.'; return;}
      get('setupRows').textContent = 'Loading setup snapshots…';
      try {
        const value = await json(`/api/laps/${id}/setup-comparison?reference_id=${encodeURIComponent(other)}`);
        if (token !== comparisonToken) return;
        get('setupCount').textContent = value.available ? `${value.rows.length} differences` : 'Unavailable';
        get('setupRows').innerHTML = value.reason ? `<p class="workspace-muted">${esc(value.reason)}</p>` : `<div class="workspace-table"><table><thead><tr><th>Setting</th><th>Selected lap</th><th>Comparison lap</th></tr></thead><tbody>${value.rows.map(row => `<tr><td>${esc(row.field.replace(/([A-Z])/g,' $1'))}</td><td>${esc(row.selected ?? 'Unknown')}</td><td>${esc(row.comparison ?? 'Unknown')}</td></tr>`).join('')}</tbody></table></div>`;
      } catch (error) { if (token === comparisonToken) get('setupRows').textContent = error.message; }
    }
  };
})();
