const L = require('./pw4.js');
const pop = '.ant-popover:not(.ant-popover-hidden)';
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  const cd=[]; page.on('response', async r=>{ if (r.url().includes('/api/v1/chart/data') && r.request().method()==='POST') { let j=null; try{ j=await r.json(); }catch(e){} const res=j&&j.result&&j.result[0]; cd.push({status:r.status(), colnames:res&&res.colnames, query: res&&res.query}); } });
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?datasource_type=table&datasource_id=${L.ids.ds}&viz_type=echarts_timeseries_bar`, {waitUntil:'networkidle'}); await page.waitForTimeout(3500);
  await step('build', async()=>{
    // metric
    await page.locator('[data-test="metrics"] >> text=Drop columns/metrics here or click').first().click(); await page.waitForTimeout(1200);
    await page.locator(`${pop} [role="tab"]`, {hasText:'Simple'}).first().click(); await page.waitForTimeout(600);
    const pane = `${pop} .ant-tabs-tabpane-active`;
    await page.locator(`${pane} .ant-select`).first().click(); await page.waitForTimeout(400);
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'총매출'}).first().click(); await page.waitForTimeout(400);
    await page.locator(`${pane} .ant-select`).nth(1).click(); await page.waitForTimeout(400);
    await page.locator(`${dd} .ant-select-item-option`, {hasText:/^SUM$/}).first().click(); await page.waitForTimeout(600);
    await page.locator(`${pop} button`, {hasText:'Save'}).first().click(); await page.waitForTimeout(800);
    await page.getByText('Update chart').first().click(); await page.waitForTimeout(3500);
    const last = cd[cd.length-1]; console.log('UI-CREATED metric colnames:', JSON.stringify(last.colnames)); console.log('query:', (last.query||'').replace(/\s+/g,' ').slice(0,300));
    await page.screenshot({path:'shots/g1_ui_metric_chart.png'});
  });
  await step('save as', async()=>{
    await page.locator('[data-test="query-save-button"]').click(); await page.waitForTimeout(1000);
    await page.locator('.ant-modal input[type="text"]').first().fill('a27 UI 막대').catch(async()=>{ await page.locator('.ant-modal input').nth(2).fill('a27 UI 막대'); }); await page.waitForTimeout(300);
    await page.locator('.ant-modal button', {hasText:/^Save$/}).first().click(); await page.waitForTimeout(3500);
    console.log('URL after save:', page.url());
  });
  await browser.close();
})();
