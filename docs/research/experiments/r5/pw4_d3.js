const L = require('./pw4.js');
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3000);
  await step('search c_1', async()=>{
    await page.locator('input[placeholder*="Search Metrics"]').fill('c_1'); await page.waitForTimeout(1000);
    console.log('SEARCH c_1 ->', await page.evaluate(()=>{ const t=document.body.innerText.replace(/\s+/g,' '); const i=t.indexOf('Columns'); return t.slice(i, i+120); }));
    await page.screenshot({path:'shots/d3_search_c1.png'});
    await page.locator('input[placeholder*="Search Metrics"]').fill('매출'); await page.waitForTimeout(800);
    console.log('SEARCH 매출 ->', await page.evaluate(()=>{ const t=document.body.innerText.replace(/\s+/g,' '); const i=t.indexOf('Columns'); return t.slice(i, i+120); }));
    await page.locator('input[placeholder*="Search Metrics"]').fill('');
  });
  await step('customize', async()=>{
    await page.getByText('Customize', {exact:true}).first().click(); await page.waitForTimeout(1500);
    await page.screenshot({path:'shots/d3_customize.png'});
    const t = await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' '));
    const i = t.indexOf('Customize columns'); console.log('CUSTOMIZE:', i>=0 ? t.slice(i, i+300) : t.slice(300, 900));
    // open customize columns
    await page.getByText('Customize columns').first().click().catch(()=>{}); await page.waitForTimeout(1000);
    console.log('CUSTOMIZE COLUMNS POPOVER:', (await L.txt(page, '.ant-popover:not(.ant-popover-hidden), .ant-modal')).slice(0,400));
    await page.screenshot({path:'shots/d3_customize_cols.png'});
  });
  await browser.close();
})();
