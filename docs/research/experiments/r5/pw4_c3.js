const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  await page.locator('[data-test="filterbar-orientation-icon"]').first().click(); await page.waitForTimeout(600);
  await page.getByText(/Add or edit filters/i).first().click(); await page.waitForTimeout(2500);
  await step('existing 상태 filter', async()=>{
    await page.locator('.ant-modal').getByText('상태', {exact:true}).first().click(); await page.waitForTimeout(1500);
    console.log('상태 filter column select text:', await page.evaluate(()=>[...document.querySelectorAll('.ant-modal .ant-select')].map(s=>(s.getAttribute('data-test')||s.getAttribute('aria-label')||'')+'='+s.innerText.replace(/\s+/g,' '))));
    await page.screenshot({path:'shots/c3_status_filter.png'});
    // open column dropdown
    await page.locator('.ant-modal [aria-label="Column select"], .ant-modal [data-test="Column select"]').first().click(); await page.waitForTimeout(800);
    console.log('COLUMN OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    console.log('COLUMN OPTION titles/html:', await page.locator(`${dd} .ant-select-item-option`).evaluateAll(els=>els.map(e=>e.getAttribute('title')+'/'+e.innerText.replace(/\s+/g,' '))));
    await page.screenshot({path:'shots/c3_column_dropdown.png'});
    await page.keyboard.press('Escape');
  });
  await step('new filter default name', async()=>{
    await page.locator('.ant-modal').getByText('New', {exact:false}).first().click().catch(()=>{}); await page.waitForTimeout(500);
    await page.screenshot({path:'shots/c3_new_menu.png'});
    console.log('NEW MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden)'));
    await page.getByText('Filter', {exact:true}).first().click().catch(()=>{}); await page.waitForTimeout(1200);
    console.log('MODAL AFTER NEW:', (await L.txt(page, '.ant-modal')).slice(0,500));
    // choose dataset
    await page.locator('.ant-modal [aria-label="Dataset"], .ant-modal [data-test="Dataset"]').last().click().catch(()=>{}); await page.waitForTimeout(600);
    console.log('DATASET OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.locator(`${dd} .ant-select-item-option`).first().click().catch(()=>{}); await page.waitForTimeout(1500);
    await page.locator('.ant-modal [aria-label="Column select"], .ant-modal [data-test="Column select"]').last().click(); await page.waitForTimeout(800);
    console.log('NEW FILTER COLUMN OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'c_2'}).first().click().catch(async()=>{ await page.locator(`${dd} .ant-select-item-option`).nth(1).click(); }); await page.waitForTimeout(1500);
    console.log('MODAL AFTER COLUMN PICK:', (await L.txt(page, '.ant-modal')).slice(0,700));
    console.log('NAME INPUT value:', await page.evaluate(()=>[...document.querySelectorAll('.ant-modal input')].map(i=>(i.getAttribute('data-test')||i.id||'')+'='+i.value).filter(x=>!x.endsWith('=')).slice(0,10)));
    await page.screenshot({path:'shots/c3_new_filter_name.png'});
  });
  await step('prefilter', async()=>{
    await page.getByText('Pre-filter available values', {exact:true}).first().click(); await page.waitForTimeout(500);
    await page.getByText(/Add pre-filter/i).first().click(); await page.waitForTimeout(1500);
    await page.screenshot({path:'shots/c3_prefilter.png'});
    console.log('PREFILTER:', (await L.txt(page, '.ant-modal')).slice(-500));
  });
  await browser.close();
})();
