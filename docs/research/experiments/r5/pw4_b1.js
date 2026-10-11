const L = require('./pw4.js');
const pop = '.ant-popover:not(.ant-popover-hidden)';
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  const cd=[]; page.on('response', async r=>{ if (r.url().includes('/api/v1/chart/data') && r.request().method()==='POST') { let j=null; try{ j=await r.json(); }catch(e){} const res=j&&j.result&&j.result[0]; cd.push({status:r.status(), rows:res&&res.rowcount, colnames:res&&res.colnames}); } });
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_bar}`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  await page.screenshot({path:'shots/b1_bar_explore.png'});
  console.log('BAR chart/data', JSON.stringify(cd));
  console.log('BAR BODY:', (await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' '))).slice(0, 1500));
  // X-axis options
  await step('xaxis', async()=>{
    await page.locator('[data-test="x_axis"] .ant-select, [data-test="x_axis"]').first().click(); await page.waitForTimeout(600);
    console.log('X-AXIS OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.keyboard.press('Escape');
  });
  // save/overwrite so that the chart has UI-generated params+query_context
  await step('save', async()=>{
    await page.locator('[data-test="query-save-button"]').click(); await page.waitForTimeout(1200);
    console.log('SAVE MODAL:', (await L.txt(page, '.ant-modal')).slice(0,300));
    await page.screenshot({path:'shots/b1_save_modal.png'});
    await page.locator('.ant-modal button', {hasText:/^Save$/}).first().click(); await page.waitForTimeout(3500);
  });
  await browser.close();
})();
