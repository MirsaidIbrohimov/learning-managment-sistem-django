const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(value = '') { this.value = value; this.dataset = {}; this.listeners = {}; this.children = []; this.textContent = ''; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this[name] = value; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
}

async function market(initial, current = initial) {
  const ids = Object.fromEntries(['ct-form','ct-balance','ct-custom','ct-submit','ct-error','ct-result','ct-recheck','ct-pricing','ct-receive','ct-pay','ct-gross','ct-savings-row','ct-savings','ct-discount','ct-rate-label','ct-rate-status','ct-offers','ct-offers-section'].map(id => [id, new Element()]));
  ids['ct-pricing'].textContent = JSON.stringify(initial);
  ids['ct-balance'].dataset.value = '50';
  ids['ct-custom'].value = '';
  const form = ids['ct-form'];
  Object.assign(form.dataset, {ready:'true',min:'1000',max:'1000000',pricingUrl:'/pricing'});
  form.action = '/checkout';
  const token = new Element('old-token'), csrf = new Element('csrf');
  const radio = new Element('10000'); radio.checked = true;
  form.querySelector = selector => selector.includes('csrf') ? csrf : token;
  form.querySelectorAll = () => [radio];
  const cost = new Element(); cost.dataset.coins = '10000';
  const document = new Element();
  document.getElementById = id => ids[id] || null;
  document.createElement = () => new Element();
  document.querySelectorAll = selector => selector === '.ct-package-cost' ? [cost] : [];
  const window = new Element(); window.location = {assign:url => { window.redirected = url; }};
  const state = {pricing:current,posts:[]};
  class FormData {
    constructor() { this.data = {}; }
    set(key, value) { this.data[key] = value; }
  }
  const fetch = async (url, options) => {
    if (url === '/pricing') return {ok:true,json:async () => ({pricing:state.pricing, pricing_token:'fresh-token',limits:[1000,1000000],ready:true})};
    state.posts.push(options.body.data);
    return {ok:true,json:async () => ({payment_url:'https://example.test/payment'})};
  };
  vm.runInNewContext(fs.readFileSync('static/js/coin_topup.js','utf8'), {
    document, window, location:{search:''}, URLSearchParams, AbortSignal, FormData, fetch,
    setInterval:() => 1, setTimeout, console,
  });
  await new Promise(resolve => setImmediate(resolve));
  return {ids,window,state,cost,custom:value => { ids['ct-custom'].value=value; ids['ct-custom'].listeners.input(); },
    submit:() => form.listeners.submit({preventDefault(){}}),
    refresh:async () => { window.listeners.focus(); await new Promise(resolve => setImmediate(resolve)); }};
}

test('an already open market replaces the old 1 som rate with the saved 2 som rate', async () => {
  const page = await market({rate:1,discounts:[]},{rate:2,discounts:[]});
  assert.equal(page.ids['ct-rate-label'].textContent, '1 tanga = 2 so‘m');
  assert.equal(page.ids['ct-receive'].textContent,'10 000 tanga');
  assert.equal(page.ids['ct-pay'].textContent,'20 000 so‘m');
  page.custom('15 000');
  assert.equal(page.ids['ct-pay'].textContent,'30 000 so‘m');
  await page.submit();
  assert.equal(page.state.posts[0].amount,'15000');
  assert.equal(page.state.posts[0].pricing_token,'fresh-token');
});

test('holiday discount cards and savings follow the threshold and disappear when disabled', async () => {
  const page = await market({rate:2,discounts:[{id:1,name:'Navroz',theme:'navruz',discount_type:'percentage',value:20,min_coins:10000}]});
  assert.equal(page.ids['ct-pay'].textContent,'16 000 so‘m');
  assert.equal(page.ids['ct-gross'].textContent,'20 000 so‘m');
  assert.equal(page.ids['ct-savings'].textContent,'4 000 so‘m');
  assert.equal(page.ids['ct-offers'].children[0].dataset.theme,'navruz');
  page.custom('9999');
  assert.equal(page.ids['ct-pay'].textContent,'19 998 so‘m');
  assert.equal(page.ids['ct-savings-row'].hidden,true);
  page.state.pricing = {rate:2,discounts:[]};
  await page.refresh();
  assert.equal(page.ids['ct-offers-section'].hidden,true);
});

test('a price change immediately before checkout updates the total and requires a second click', async () => {
  const page = await market({rate:2,discounts:[]});
  page.state.pricing = {rate:3,discounts:[]};
  await page.submit();
  assert.equal(page.state.posts.length,0);
  assert.equal(page.ids['ct-pay'].textContent,'30 000 so‘m');
  assert.match(page.ids['ct-error'].textContent,/yangilandi/);
  await page.submit();
  assert.equal(page.state.posts.length,1);
  assert.equal(page.window.redirected,'https://example.test/payment');
});

test('1000 custom coins submit successfully and fewer than 1000 are blocked', async () => {
  const page = await market({rate:2,discounts:[]});
  page.custom('1\u202f000');
  assert.equal(page.ids['ct-pay'].textContent,'2 000 so‘m');
  assert.equal(page.ids['ct-submit'].disabled,false);
  await page.submit();
  assert.equal(page.state.posts[0].amount,'1000');
  const invalid = await market({rate:2,discounts:[]});
  invalid.custom('999');
  assert.equal(invalid.ids['ct-submit'].disabled,true);
  assert.match(invalid.ids['ct-error'].textContent,/1 000 tanga/);
  await invalid.submit();
  assert.equal(invalid.state.posts.length,0);
});
