(() => {
  const dialog = document.getElementById('arc-tour');
  if (!dialog) return;
  const title = document.getElementById('arc-tour-title');
  const description = document.getElementById('arc-tour-description');
  const progress = document.getElementById('tour-progress');
  const progressBar = document.getElementById('tour-progress-bar');
  const back = document.getElementById('tour-back');
  const next = document.getElementById('tour-next');
  const finish = document.getElementById('tour-skip');
  const close = document.getElementById('tour-close');
  const steps = [
    {title:'Welcome to Arc', description:'Arc has three independent tools. You can use any of them without first completing another part of the app.'},
    {title:'M&A Analysis', description:'Compare a named buyer and target across financial, business, cultural, and integration considerations. Uploading documents is optional; Arc can start with public research.'},
    {title:'Business Insights', description:'Research a company or industry from a business perspective: business model, market position, competitors, customer and product signals, growth opportunities, and operating risks.'},
    {title:'Discovery', description:'Find comparable companies by industry and geography, then narrow results by annual revenue, estimated company value, or employee count. This does not depend on M&A Analysis.'},
    {title:'Working with results', description:'Open source links to verify claims, save reports for later in this browser, and export an M&A investigation as a PDF when you need a shareable brief.'}
  ];
  let current = 0;
  function render() {
    const step = steps[current];
    title.textContent = step.title;
    description.textContent = step.description;
    progress.textContent = `${current + 1} of ${steps.length}`;
    progressBar.style.width = `${((current + 1) / steps.length) * 100}%`;
    back.disabled = current === 0;
    next.textContent = current === steps.length - 1 ? 'Finish tour' : 'Next';
  }
  async function markSeen() {
    try { await window.ArcStore?.setPreference({key:'tourCompleted', value:true}); } catch (error) { /* Tour remains usable even if saving settings fails. */ }
  }
  function openTour() {
    current = 0; render();
    if (!dialog.open) dialog.showModal();
  }
  document.querySelectorAll('[data-tour-open]').forEach(button => button.addEventListener('click', openTour));
  back.addEventListener('click', () => { if (current > 0) { current -= 1; render(); } });
  next.addEventListener('click', async () => {
    if (current < steps.length - 1) { current += 1; render(); }
    else { await markSeen(); dialog.close(); }
  });
  finish.addEventListener('click', async () => { await markSeen(); dialog.close(); });
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  // Introduce the walkthrough once in the signed-in workspace. It remains available from the header.
  if (!document.body.classList.contains('public-site')) {
    window.addEventListener('load', async () => {
      try {
        const completed = await window.ArcStore?.getPreference('tourCompleted');
        if (completed !== true) openTour();
      } catch (error) { /* Don't block the workspace if browser preferences are unavailable. */ }
    }, {once:true});
  }
})();
