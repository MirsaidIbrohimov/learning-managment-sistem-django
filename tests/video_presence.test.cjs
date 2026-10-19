const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = new Map();
const events = {addEventListener(name, fn) {listeners.set(name, fn);}, removeEventListener(name, fn) {if (listeners.get(name) === fn) listeners.delete(name);}};
const window = {...events, innerWidth:1440, innerHeight:900};
const document = {...events};
vm.runInNewContext(fs.readFileSync('static/js/video_presence.js', 'utf8'), {window, document, Math});
let width=1440, height=900, offsetX=0, offsetY=0;
const modal={style:{}, get offsetWidth(){return parseFloat(this.style.width);}, get offsetHeight(){return Math.min(300, parseFloat(this.style.maxHeight));}, querySelector(){return {focus(){}};}};
const overlay={...events, classList:{add(){}}, querySelector(){return modal;}, getBoundingClientRect(){return {left:offsetX, top:offsetY, width, height};}};
function assertFits(){
 const x=parseFloat(modal.style.left), y=parseFloat(modal.style.top);
 assert(x>=0 && y>=0);
 assert(x+modal.offsetWidth<=width+1);
 assert(y+modal.offsetHeight<=height+1);
}
let last='';
for(let i=0;i<100;i++){
 const clean=window.placeVideoPresence(overlay);assertFits();
 const current=modal.style.left+':'+modal.style.top;
 assert.notEqual(current,last,'Successive prompts must change anchors');last=current;
 clean();assert.equal(listeners.size,0,'Listeners must be cleaned up');
}
for(const size of [[320,568],[568,260],[240,180],[1920,1080]]){
 [width,height]=size;window.innerWidth=width;window.innerHeight=height;
 const clean=window.placeVideoPresence(overlay);assertFits();
 width=280;height=210;window.innerWidth=width;window.innerHeight=height;
 listeners.get('resize')();assertFits();clean();
}
width=390;height=700;window.innerWidth=390;window.innerHeight=700;
window.visualViewport={...events,offsetLeft:20,offsetTop:40,width:300,height:400};
const clean=window.placeVideoPresence(overlay);assertFits();
assert(parseFloat(modal.style.left)>=20);
assert(parseFloat(modal.style.top)>=40);
assert(parseFloat(modal.style.left)+modal.offsetWidth<=320);
assert(parseFloat(modal.style.top)+modal.offsetHeight<=440);
clean();assert.equal(listeners.size,0);
console.log('PASS: 100 non-repeating positions, mobile/landscape, resize, visual viewport, cleanup.');
