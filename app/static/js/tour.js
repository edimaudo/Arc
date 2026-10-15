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
    {title:'Acquisition Analysis', description:'Choose a buyer and target. Arc researches both companies and compares financial evidence, products, markets, customer overlap, culture and integration considerations. Documents are optional; they add evidence but do not start or unlock the analysis.'},
    {title:'Business Insights', description:'Understand how one company or industry operates and competes. Get a business brief covering its model, market trends, customers and products, competitors, operational risks, growth opportunities, practical actions and metrics. It does not create a peer-company shortlist.'},
    {title:'Discovery', description:'Choose a company already researched in Arc and a geography. Discovery returns the top five aligned companies using available revenue, valuation, employee count, industry, business model and cultural/audience context. Results appear only after you select Find comparable companies.'},
    {title:'Working with results', description:'Use linked sources to verify claims. Company and industry research is saved in this browser, and Acquisition analyses can be exported as PDF. If live research is temporarily unavailable, Arc shows a clearly labelled starter analysis or an actionable retry message rather than pretending research succeeded.'}
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
