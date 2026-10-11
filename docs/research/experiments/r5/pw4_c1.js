const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  const cd=[]; page.on('response', async r=>{ if (r.url().includes('/api/v1/chart/data') && r.request().method()==='POST') { let j=null; try{ j=await r.json(); }catch(e){} const res=j&&j.result&&j.result[0]; cd.push({status:r.status(), rows:res&&res.rowcount, colnames:res&&res.colnames}); } });
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4500);
  await page.screenshot({path:'shots/c1_dash.png'});
  console.log('DASH chart/data', JSON.stringify(cd));
  console.log('FILTER BAR TEXT:', await L.txt(page, '[data-test="filter-bar"]'));
  console.log('TABLE HEADERS in dashboard:', (await page.locator('[data-test="chart-container"] [role="columnheader"], [data-test="chart-container"] th').allInnerTexts()).join(' | '));
  // apply team filter
  await step('apply', async()=>{
    await page.locator('[data-test="NATIVE_FILTER-a27team"] .ant-select-selector, [data-test="NATIVE_FILTER-a27team"]').first().click(); await page.waitForTimeout(700);
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'팀1'}).first().click(); await page.keyboard.press('Escape');
    await page.locator('[data-test="filter-bar__apply-button"]').click(); await page.waitForTimeout(3500);
    await page.screenshot({path:'shots/c1_dash_filtered.png'});
    console.log('FILTER BAR AFTER APPLY:', await L.txt(page, '[data-test="filter-bar"]'));
  });
  await step('indicator', async()=>{
    // chart filter indicator badge
    const badge = page.locator('[data-test="filter-indicator"], [data-test="applied-filter-indicator"], .filter-indicator, [data-test="filters-indicator"], [data-test="incompatible-filters-indicator"]');
    console.log('indicator count', await badge.count());
    const trig = page.locator('[data-test="applied-filter-count"], [data-test="filter-count"], [data-test*="indicator"]').first();
    await trig.hover().catch(()=>{}); await page.waitForTimeout(1200);
    console.log('INDICATOR HOVER:', await L.txt(page, '.ant-popover:not(.ant-popover-hidden), .ant-tooltip:not(.ant-tooltip-hidden)'));
    await page.screenshot({path:'shots/c1_indicator.png'});
  });
  await step('chart-menu', async()=>{
    await page.mouse.move(100,100); 
    const chart = page.locator('.dashboard-component-chart-holder').first(); await chart.hover(); await page.waitForTimeout(500);
    await chart.locator('[data-test="more-vert-trigger"], [aria-label="more-vert"], .ant-dropdown-trigger').first().click(); await page.waitForTimeout(800);
    console.log('CHART MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden)'));
    await page.getByText('View query', {exact:true}).first().click(); await page.waitForTimeout(2500);
    console.log('DASH VIEW QUERY:', (await L.txt(page, '.ant-modal')).slice(0,700));
    await page.screenshot({path:'shots/c1_dash_view_query.png'});
    await page.keyboard.press('Escape');
  });
  await browser.close();
})();
