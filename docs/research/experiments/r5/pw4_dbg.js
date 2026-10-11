const L = require('./pw4.js');
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'}); await page.waitForTimeout(2500);
  console.log(await page.evaluate(()=>[...document.querySelectorAll('header button, [class*="header"] button, button')].slice(0,14).map(b=>(b.getAttribute('data-test')||'')+'|'+(b.getAttribute('aria-label')||'')+'|'+b.innerHTML.replace(/\s+/g,' ').slice(0,120))));
  await browser.close();
})();
