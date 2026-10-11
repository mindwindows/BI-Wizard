const L = require('./pw4.js');
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  const cd=[]; page.on('response', async r=>{ if (r.url().includes('/api/v1/chart/data') && r.request().method()==='POST') { let j=null; try{ j=await r.json(); }catch(e){} const res=j&&j.result&&j.result[0]; cd.push({status:r.status(), rows:res&&res.rowcount, colnames:res&&res.colnames, err:res&&res.error}); } });
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4500);
  console.log('DASH chart/data AFTER RENAME', JSON.stringify(cd));
  console.log('TABLE HEADERS after rename:', (await page.locator('[data-test="chart-container"] [role="columnheader"], [data-test="chart-container"] th').allInnerTexts()).join(' | '));
  console.log('FILTER BAR:', await L.txt(page, '[data-test="filter-bar"]'));
  await page.screenshot({path:'shots/e1_dash_after_rename.png'});
  cd.length=0;
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_bar}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3500);
  console.log('BAR explore after rename: ', JSON.stringify(cd), (await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' '))).slice(380, 560));
  await browser.close();
})();
