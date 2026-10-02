// Fast catalogue checks without starting a browser or changing user preferences.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.resolve(__dirname, '..');
const context = {window: {F1_INITIAL_LANGUAGE:'en'}, localStorage:{getItem:()=>null},
  navigator:{language:'en'}, document:{documentElement:{},addEventListener:()=>{}}, console};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'frontend/static/i18n_catalog.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'frontend/static/i18n.js'),'utf8'),context);
const t = context.window.I18n.t;
const assert = require('assert');
assert.equal(t('Lap analysis','ja'),'ラップ分析');
assert.equal(t('ラップ分析','en'),'Lap analysis');
assert.equal(t('Lap 7 · Bahrain · 1:30.253','ja'),'ラップ 7 · バーレーン · 1:30.253');
assert.equal(t('Recording: waiting','ja'),'記録: 待機中');
assert.equal(t('Clean laps: same compound/setup, fuel ±3 kg, wear ±3%, starting ERS ±10%','ja'),
  '同じタイヤ・セットアップの有効ラップ：燃料±3kg、摩耗±3%、開始時ERS±10%');
assert.equal(t('1:30.253 · 984.75 m · 43.7%','ja'),'1:30.253 · 984.75 m · 43.7%');
assert.equal(t('my_lap_id/setup_123.json','ja'),'my_lap_id/setup_123.json');
assert.equal(t('Lap 8 · SELECTED · 1 lap · VALID','ja'),'ラップ 8 · 選択中 · 1 周 · 有効');
assert.equal(t('最速3%以内から8周を比較。各地点は中央値と多数決で構成。','en'),
  'Compare 8 laps within 3% of the fastest. Use the median and majority input at each location.');
assert.equal(t('4区間でERSを使用し、フィニッシュSOCを約7.5%にします。','en'),
  'Use ERS in 4 sections with a target finish SOC of about 7.5%.');
assert.equal(t('Waiting for a completed lap...','ja'),'完了したラップの記録を待っています…');
assert.equal(t('Observed association; weather, traffic and driving differences can still affect pace','ja'),
  '記録上の関連です。天候・交通・操作の違いもペースに影響します');
console.log('Localization catalogue checks passed.');
if (process.argv.includes('--inventory')) {
  const source=fs.readFileSync(path.join(root,'.runtime/localization-static.txt'),'utf8').split(/\r?\n/);
  for (const lang of ['ja','en']) {
    const remaining=source.filter(s => (lang==='ja'?/[a-zA-Z]{3}/:/[\u3040-\u30ff\u4e00-\u9fff]/).test(s) && t(s,lang)===s);
    console.log(lang,'unchanged static strings:',remaining);
  }
}
