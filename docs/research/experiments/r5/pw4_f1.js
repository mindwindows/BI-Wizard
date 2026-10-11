const L = require('./pw4.js');
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  const cd=[]; page.on('response', async r=>{ if (r.url().includes('/api/v1/chart/data') && r.request().method()==='POST') { let j=null; try{ j=await r.json(); }catch(e){} const res=j&&j.result&&j.result[0]; cd.push({status:r.status(), colnames:res&&res.colnames, query: res&&res.query}); } });
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_bar}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3500);
  await step('remove dimension', async()=>{
    await page.locator('[data-test="groupby"] [aria-label="close"], [data-test="groupby"] .anticon-close').first().click(); await page.waitForTimeout(600);
    await page.getByText('Update chart').first().click(); await page.waitForTimeout(3500);
    console.log('LAST chart/data colnames:', JSON.stringify(cd[cd.length-1].colnames));
    console.log('LAST query:', (cd[cd.length-1].query||'').replace(/\s+/g,' ').slice(0,400));
    await page.screenshot({path:'shots/f1_bar_nogroup.png'});
  });
  await browser.close();
})();
