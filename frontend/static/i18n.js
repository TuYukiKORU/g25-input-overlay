/* Shared display localization. IDs, API payloads and saved telemetry stay unchanged. */
(function () {
  'use strict';
  const pairs = window.F1_TRANSLATIONS.pairs;
  const key = 'f1-language-v1';
  let stored;
  try { stored = localStorage.getItem(key); } catch {}
  let language = window.F1_INITIAL_LANGUAGE || stored || (navigator.language.startsWith('ja') ? 'ja' : 'en');
  if (!['en', 'ja'].includes(language)) language = 'en';
  const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const catalogs = {};
  for (const target of ['en', 'ja']) {
    const entries = new Map();
    for (const [en, ja] of pairs) {
      const source = target === 'ja' ? en : ja;
      if (!entries.has(source)) entries.set(source, target === 'ja' ? ja : en);
    }
    const ordered = [...entries.keys()].sort((a, b) => b.length - a.length);
    const expressions = ordered.map(source => {
      const first = /^[a-zA-Z0-9]/.test(source) ? '(?<![a-zA-Z0-9_])' : '';
      const last = /[a-zA-Z0-9]$/.test(source) ? '(?![a-zA-Z0-9_])' : '';
      return first + escape(source) + last;
    });
    catalogs[target] = {entries, pattern: new RegExp(expressions.join('|'), 'g')};
  }
  function t(value, target = language) {
    if (value == null) return '';
    let text = String(value);
    const catalog = catalogs[target];
    for (const [pattern, replacement] of window.F1_TRANSLATIONS.dynamic?.[target] || []) {
      text = text.replace(new RegExp(pattern, 'g'), replacement);
    }
    if (catalog.entries.has(text)) return catalog.entries.get(text);
    return text.replace(catalog.pattern, match => catalog.entries.get(match));
  }
  // All distance/time graphs use 2D canvas. Translate labels and their measured
  // widths together so localized labels fit the same boxes.
  const canvas = window.CanvasRenderingContext2D?.prototype;
  if (canvas) for (const method of ['fillText', 'strokeText', 'measureText']) {
    const original = canvas[method];
    canvas[method] = function (text, ...args) { return original.call(this, t(text), ...args); };
  }
  const originals = new WeakMap(), attributes = new WeakMap();
  const ignored = element => element?.closest('script,style,textarea,[data-i18n-ignore]');
  let observer, pending = false;
  function translateDocument() {
    observer?.disconnect();
    document.documentElement.lang = language;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (ignored(node.parentElement) || !node.data.trim()) continue;
      let record = originals.get(node);
      if (!record || node.data !== record.translated) record = {source: node.data};
      record.translated = t(record.source);
      if (node.data !== record.translated) node.data = record.translated;
      originals.set(node, record);
    }
    for (const element of document.querySelectorAll('[title],[placeholder],[aria-label]')) {
      // User-written notes are never translated, but their placeholders are UI.
      if (element.closest('script,style,[data-i18n-ignore]')) continue;
      const records = attributes.get(element) || {};
      for (const name of ['title', 'placeholder', 'aria-label']) {
        if (!element.hasAttribute(name)) continue;
        const value = element.getAttribute(name);
        let record = records[name];
        if (!record || value !== record.translated) record = {source: value};
        record.translated = t(record.source);
        if (value !== record.translated) element.setAttribute(name, record.translated);
        records[name] = record;
      }
      attributes.set(element, records);
    }
    // The title is outside the body walker.
    const title = document.querySelector('title');
    if (title) {
      const text = title.firstChild;
      if (text) {
        let record = originals.get(text);
        if (!record || text.data !== record.translated) record = {source: text.data};
        record.translated = t(record.source); text.data = record.translated; originals.set(text, record);
      }
    }
    const select = document.getElementById('languageSelect');
    if (select) select.value = language;
    observer?.observe(document.body, {subtree: true, childList: true, characterData: true,
      attributes: true, attributeFilter: ['title', 'placeholder', 'aria-label']});
  }
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; translateDocument(); });
  }
  async function setLanguage(value) {
    if (!['en', 'ja'].includes(value)) throw new Error('Unsupported language');
    if (window.F1_DESKTOP_MODE) {
      const response = await fetch('/api/desktop/preferences', {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({language: value})});
      if (!response.ok) throw new Error('Could not save language preference');
    }
    try { localStorage.setItem(key, value); } catch {}
    language = value;
    translateDocument();
    window.dispatchEvent(new Event('languagechange'));
    window.dispatchEvent(new Event('resize'));
    return value;
  }
  window.I18n = {t, setLanguage, refresh: schedule, get language() { return language; }};
  document.documentElement.lang = language;
  document.addEventListener('DOMContentLoaded', () => {
    const main = document.querySelector('main');
    if (main) {
      const toolbar = document.createElement('div');
      toolbar.className = 'language-toolbar'; toolbar.dataset.i18nIgnore = '';
      toolbar.innerHTML = '<label for="languageSelect">Language / 言語 <select id="languageSelect" aria-label="Language / 言語"><option value="ja">日本語</option><option value="en">English</option></select></label><span id="languageStatus" role="status"></span>';
      main.prepend(toolbar);
      toolbar.querySelector('select').value = language;
      toolbar.querySelector('select').addEventListener('change', async event => {
        const select = event.target; select.disabled = true;
        document.getElementById('languageStatus').textContent = '';
        try { await setLanguage(select.value); }
        catch (error) { select.value = language; document.getElementById('languageStatus').textContent = t(error.message); }
        finally { select.disabled = false; }
      });
    }
    observer = new MutationObserver(schedule);
    translateDocument();
  });
})();
