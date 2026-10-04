(() => {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem('arc-theme');
  const savedScale = localStorage.getItem('arc-scale');
  if (savedTheme) root.dataset.theme = savedTheme;
  if (savedScale) root.dataset.textScale = savedScale;

  document.querySelectorAll('[data-font]').forEach(btn => {
    btn.addEventListener('click', () => {
      root.dataset.textScale = btn.dataset.font;
      localStorage.setItem('arc-scale', btn.dataset.font);
      document.querySelectorAll('[data-font]').forEach(x => x.classList.toggle('active', x === btn));
    });
  });

  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = theme;
    localStorage.setItem('arc-theme', theme);
  });
})();
