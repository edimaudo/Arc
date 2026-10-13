(() => {
  const root = document.documentElement;
  const setActiveFont = value => document.querySelectorAll('[data-font]').forEach(btn => btn.classList.toggle('active', btn.dataset.font === String(value)));

  async function loadPreferences() {
    try {
      const [theme, scale] = await Promise.all([ArcStore.getPreference('theme'), ArcStore.getPreference('textScale')]);
      if (theme === 'light' || theme === 'dark') root.dataset.theme = theme;
      if (['0.9', '1', '1.15'].includes(String(scale))) root.dataset.textScale = String(scale);
      setActiveFont(root.dataset.textScale || '1');
    } catch (error) {
      console.error('Arc browser preferences could not be loaded:', error);
    }
  }

  document.querySelectorAll('[data-font]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const value = btn.dataset.font;
      root.dataset.textScale = value;
      setActiveFont(value);
      try { await ArcStore.setPreference({key: 'textScale', value}); }
      catch (error) { console.error('Arc could not save this preference:', error); }
    });
  });

  document.getElementById('theme-toggle')?.addEventListener('click', async () => {
    const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = theme;
    try { await ArcStore.setPreference({key: 'theme', value: theme}); }
    catch (error) { console.error('Arc could not save this preference:', error); }
  });

  loadPreferences();
})();
