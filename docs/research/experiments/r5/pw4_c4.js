const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  await page.locator('[data-test="filterbar-orientation-icon"]').first().click(); await page.waitForTimeout(600);
  await page.getByText(/Add or edit filters/i).first().click(); await page.waitForTimeout(2500);
  const sel = i => page.locator('.ant-modal .ant-select').nth(i);
  await step('existing column dropdown', async()=>{
    await page.locator('.ant-modal').getByText('상태', {exact:true}).first().click(); await page.waitForTimeout(1200);
    // after selecting 상태 filter, modal has 3 selects visible (active pane only?)
    console.log('n selects', await page.locator('.ant-modal .ant-select').count());
    await page.locator('.ant-modal .ant-select').last().click(); await page.waitForTimeout(900);
    console.log('COLUMN OPTIONS:', await page.locator(`${dd} .ant-select-item-option`).evaluateAll(els=>els.map(e=>(e.getAttribute('title')||'')+' / '+e.innerText.replace(/\s+/g,' '))));
    await page.screenshot({path:'shots/c4_column_dropdown.png'});
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
  });
  await step('new filter', async()=>{
    await page.getByRole('button', {name:/New/}).first().click(); await page.waitForTimeout(600);
    await page.getByText('Add filter', {exact:true}).first().click(); await page.waitForTimeout(1500);
    const n = await page.locator('.ant-modal .ant-select').count(); console.log('selects after new', n);
    await page.screenshot({path:'shots/c4_new_filter1.png'});
    // dataset select is the visible one for the new filter: use last-3.. indexes
    const dsSel = page.locator('.ant-modal .ant-select').nth(n-2); await dsSel.click(); await page.waitForTimeout(800);
    console.log('DATASET OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.locator(`${dd} .ant-select-item-option`).first().click(); await page.waitForTimeout(1500);
    await page.locator('.ant-modal .ant-select').last().click(); await page.waitForTimeout(900);
    console.log('NEW FILTER COLUMN OPTIONS:', await page.locator(`${dd} .ant-select-item-option`).evaluateAll(els=>els.map(e=>(e.getAttribute('title')||'')+' / '+e.innerText.replace(/\s+/g,' '))));
    await page.screenshot({path:'shots/c4_new_filter2.png'});
    await page.locator(`${dd} .ant-select-item-option`).nth(1).click(); await page.waitForTimeout(1500);
    console.log('INPUTS:', await page.evaluate(()=>[...document.querySelectorAll('.ant-modal input')].map(i=>(i.getAttribute('data-test')||i.id||i.type)+'='+i.value).slice(0,12)));
    console.log('LEFT LIST:', (await L.txt(page, '.ant-modal')).slice(0,200));
    await page.screenshot({path:'shots/c4_new_filter3.png'});
  });
  await step('prefilter', async()=>{
    await page.locator('.ant-modal').getByText('Pre-filter available values').first().click(); await page.waitForTimeout(800);
    await page.getByText(/Add pre-filter/i).first().click(); await page.waitForTimeout(1500);
    await page.screenshot({path:'shots/c4_prefilter.png'});
    console.log('PREFILTER:', (await L.txt(page, '.ant-modal')).slice(-400));
  });
  await browser.close();
})();
