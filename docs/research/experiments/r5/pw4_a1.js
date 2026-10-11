const L = require('./pw4.js');
(async()=>{
  const {browser, page} = await L.start();
  const errs=[]; page.on('pageerror', e=>errs.push(String(e).slice(0,150)));
  const cd=[]; page.on('response', async r=>{ if (r.url().includes('/api/v1/chart/data') && r.request().method()==='POST') { let j=null; try{ j=await r.json(); }catch(e){} const res=j&&j.result&&j.result[0]; cd.push({status:r.status(), rows:res&&res.rowcount, colnames:res&&res.colnames}); } });
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'});
  await page.waitForTimeout(4000);
  await page.screenshot({path:'shots/a1_explore_table.png'});
  const body = await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' ').slice(0,3000));
  console.log('BODY:', body);
  console.log('chart/data', JSON.stringify(cd), 'errs', errs);
  await browser.close();
})();
