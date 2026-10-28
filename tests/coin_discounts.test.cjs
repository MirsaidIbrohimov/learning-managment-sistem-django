const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('admin preview explains rate changes and holiday savings before saving', () => {
  const element = value => ({value, textContent:'', dataset:{}, listeners:{},
    addEventListener(name, fn){this.listeners[name] = fn;},
    dispatchEvent(event){this.listeners[event.type]?.();}});
  const fields = {name:element('Navröz'),theme:element('navruz'),discount_type:element('percentage'),
    value:element('20'),min_coins:element('10000')};
  const ids = Object.fromEntries(['id_som_per_coin','cd-campaign-form','cd-saved-rate','cd-rate-example',
    'cd-preview','cd-preview-name','cd-preview-min','cd-preview-value','cd-preview-old','cd-preview-pay',
    'cd-preview-coins','cd-value-unit'].map(id => [id,element('')]));
  ids.id_som_per_coin.value = '2';
  ids['cd-saved-rate'].textContent = '2';
  ids['cd-campaign-form'].elements = fields;
  const icon = element('');
  ids['cd-preview'].querySelector = () => icon;
  vm.runInNewContext(fs.readFileSync('static/js/coin_discounts.js','utf8'), {
    document:{getElementById:id => ids[id]},Intl,Event,
  });
  assert.match(ids['cd-rate-example'].textContent,/20\s000/);
  assert.match(ids['cd-preview-pay'].textContent,/16\s000/);
  assert.equal(ids['cd-preview'].dataset.theme,'navruz');
  assert.equal(icon.textContent,'🌷');
  ids.id_som_per_coin.value = '3';
  ids.id_som_per_coin.listeners.input();
  assert.match(ids['cd-rate-example'].textContent,/30\s000/);
  fields.theme.value = 'newyear';
  fields.discount_type.value = 'fixed';
  fields.value.value = '5000';
  fields.min_coins.value = '50000';
  ids['cd-campaign-form'].listeners.input();
  assert.equal(ids['cd-preview'].dataset.theme,'newyear');
  assert.equal(icon.textContent,'🎄');
  assert.match(ids['cd-preview-pay'].textContent,/95\s000/);
  assert.equal(ids['cd-value-unit'].textContent,'(söm)');
});
