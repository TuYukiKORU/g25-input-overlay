// Exercise actual chart helpers with the corrupted-data shape and valid motion.
const assert = require('node:assert/strict');
const {hasDrivingPath, accelerationSeries} = require('../frontend/static/motion_data.js');
const samples = [100, 130, 160, 130, 100].map((speed, index) => ({
  lap_distance: index * 10, lap_time_ms: index * 1000, speed,
  position: {x: 0, z: 0}, longitudinal_g: 0
}));
const original = JSON.stringify(samples);
assert.equal(hasDrivingPath(samples), false);
const repaired = accelerationSeries(samples);
assert.equal(repaired.estimated, true);
assert.ok(repaired.samples[0].acceleration_g > .8);
assert.ok(repaired.samples.at(-1).acceleration_g < -.8);
assert.equal(JSON.stringify(samples), original);
assert.equal(accelerationSeries(samples.slice(1, 3), samples).estimated, true);
const recorded = samples.map((point, index) => ({...point, position: {x: index * 10, z: index * 5}, longitudinal_g: .125}));
assert.equal(hasDrivingPath(recorded), true);
assert.equal(accelerationSeries(recorded).estimated, false);
assert.ok(accelerationSeries(recorded).samples.every(point => point.acceleration_g === .125));
const coasting = recorded.map(point => ({...point, longitudinal_g: 0}));
assert.equal(accelerationSeries(coasting).estimated, false);
const legacy = recorded.map(({longitudinal_g, ...point}) => point);
assert.equal(accelerationSeries(legacy).estimated, true);
assert.equal(hasDrivingPath([{position: {x: NaN, z: Infinity}}]), false);
assert.equal(accelerationSeries([{speed: null}]).samples.length, 0);
console.log('Motion chart checks passed: estimates, valid recorded G, zoom, and missing positions.');
