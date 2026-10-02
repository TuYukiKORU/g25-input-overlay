document.addEventListener('DOMContentLoaded', () => {
  const main = document.querySelector('main');
  if (!main) return;
  const demo = window.F1_DESKTOP_MODE === 'test';
  const toolbar = document.createElement('div');
  toolbar.className = 'desktop-toolbar';
  const menu = document.createElement('details');
  menu.id = 'desktopFileMenu';
  menu.className = 'desktop-file-menu';
  const summary = document.createElement('summary');
  summary.textContent = 'File';
  menu.append(summary);
  const actions = document.createElement('div');
  actions.className = 'desktop-file-actions';
  const status = document.createElement('span');
  status.setAttribute('role', 'status');
  const options = [
    [demo ? 'Open my recordings' : 'Open test laps', 'open_other_mode'],
    ['Open recordings folder', 'open_recordings_folder'],
    ['Open logs folder', 'open_logs_folder'],
    ['Exit', 'close_window']
  ];
  for (const [label, action] of options) {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = label; button.dataset.desktopAction = action;
    button.disabled = true;
    button.addEventListener('click', async () => {
      button.disabled = true; status.textContent = '';
      try {
        await window.pywebview.api[action]();
        menu.open = false;
      } catch {
        status.textContent = window.I18n.t('Could not open the desktop action.');
      } finally { button.disabled = false; }
    });
    actions.append(button);
  }
  actions.append(status); menu.append(actions); toolbar.append(menu);
  const help = document.createElement('a');
  help.textContent = 'User manual';
  help.className = 'desktop-manual-link';
  const updateHelp = () => { help.href = `/manual?lang=${window.I18n?.language || 'en'}`; };
  updateHelp();
  window.addEventListener('languagechange', updateHelp);
  toolbar.append(help);
  const language = main.querySelector('.language-toolbar');
  if (language) toolbar.append(language);
  main.prepend(toolbar);
  const enableActions = () => {
    if (window.pywebview?.api) actions.querySelectorAll('button').forEach(button => { button.disabled = false; });
  };
  window.addEventListener('pywebviewready', enableActions);
  enableActions();
  document.addEventListener('click', event => { if (!menu.contains(event.target)) menu.open = false; });
  menu.addEventListener('keydown', event => { if (event.key === 'Escape') { menu.open = false; summary.focus(); } });
  const banner = document.createElement('aside');
  banner.id = 'desktopStatus';
  banner.className = `desktop-status${demo ? ' test' : ''}`;
  const title = document.createElement('strong');
  title.textContent = demo ? 'Test laps · Recording off' : 'My recordings · UDP 20777';
  const detail = document.createElement('span');
  detail.textContent = demo
    ? 'Real previous laps in a separate test copy. Use File → Open my recordings to record new laps.'
    : 'Use File → Open test laps to try the app without the game. File → Open recordings folder shows your saved data.';
  banner.append(title, detail);
  const header = main.querySelector('header');
  if (header) header.after(banner); else main.prepend(banner);
});
