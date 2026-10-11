const L = require('./pw4.js');
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  const cd=[]; page.on('response', async r=>{ if (r.url().includes('/api/v1/chart/data') && r.request().method()==='POST') { let j=null; try{ j=await r.json(); }catch(e){} const res=j&&j.result&&j.result[0]; cd.push({status:r.status(), colnames:res&&res.colnames, query: res&&res.query}); } });
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_ui}`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  const last = cd[cd.length-1]; console.log('AFTER RENAME (saved UI chart) colnames:', JSON.stringify(last.colnames), 'status', last.status);
  console.log('Explore metrics control text:', await page.locator('[data-test="metrics"]').first().innerText().then(t=>t.replace(/\s+/g,' ')));
  await page.screenshot({path:'shots/g3_after_rename_ui_chart.png'});
  await browser.close();
})();
