/* Motion display helpers. Estimates never change the saved telemetry. */
(function (root) {
  'use strict';
  const finite = value => value != null && Number.isFinite(Number(value));

  function hasDrivingPath(samples) {
    const positions = samples.filter(point => finite(point.position?.x) && finite(point.position?.z));
    if (positions.length < 2) return false;
    const first = positions[0].position;
    return positions.some(point => Math.hypot(Number(point.position.x) - Number(first.x),
      Number(point.position.z) - Number(first.z)) > .5);
  }

  function accelerationSeries(points, fullSamples = points) {
    const source = fullSamples.filter(point => finite(point.speed));
    // The old 2026 decoder could record a collapsed path and constant zero G
    // while the speed changed. Those zeros are not measured acceleration.
    const speeds = source.map(point => Number(point.speed));
    const brokenZeroMotion = source.length > 1 && !hasDrivingPath(fullSamples) &&
      source.every(point => finite(point.longitudinal_g) && Number(point.longitudinal_g) === 0) &&
      Math.max(...speeds) - Math.min(...speeds) > 1;
    const usable = points.filter(point => finite(point.speed));
    let estimated = false;
    const samples = usable.map((point, index) => {
      if (!brokenZeroMotion && finite(point.longitudinal_g)) {
        return {...point, acceleration_g: Number(point.longitudinal_g)};
      }
      estimated = true;
      const before = usable[Math.max(0, index - 2)], after = usable[Math.min(usable.length - 1, index + 2)];
      const elapsed = (Number(after.lap_time_ms) - Number(before.lap_time_ms)) / 1000;
      const derived = elapsed > 0 ? ((Number(after.speed) - Number(before.speed)) / 3.6) / elapsed / 9.80665 : 0;
      return {...point, acceleration_g: Math.max(-6, Math.min(6, derived))};
    });
    return {samples, estimated};
  }

  const helpers = {hasDrivingPath, accelerationSeries};
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  else root.TelemetryMotion = helpers;
})(typeof window !== 'undefined' ? window : globalThis);
