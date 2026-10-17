const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element {
  constructor(){this.children=[];this.value='';this.handlers={};this.classList={add(){},toggle(){return true},contains(){return false}};}
  append(...elements){for(const el of elements){el.parentElement=this;this.children.push(el)}}
  setAttribute(key,value){this[key]=value}
  addEventListener(key,fn){this.handlers[key]=fn}
  dispatchEvent(){}
  remove(){this.removed=true}
}
const document={createElement:()=>new Element(),addEventListener(){}};
test('Python editor preserves version/stdin and terminates execution on completion',()=>{
  let call,terminated=false;
  const runtime={start(root,options,receive){call={options,receive};return()=>{terminated=true}}};
  const context={document,window:{addEventListener(){},HomeworkPython:runtime},HomeworkPython:runtime,Event:class{},setTimeout:()=>1,clearTimeout(){}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('static/js/homework_code.js','utf8'),context);
  const project={language:'python',code:'print(input())',version:'3.13',stdin:'Ali\n'};
  const root=new Element(),editor=context.window.HomeworkCode.create(root,project,true);
  assert.deepEqual(JSON.parse(JSON.stringify(editor.get())),project);
  root.children[0].children.find(el=>el.textContent?.includes('Ishga tushirish')).handlers.click();
  assert.equal(call.options.version,'3.13');assert.equal(call.options.stdin,'Ali\n');
  call.receive({type:'running',text:'3.13'});call.receive({type:'stdout',text:'Ali\n'});call.receive({type:'done'});
  assert.equal(terminated,true);
  editor.set({language:'python',code:'print(42)',version:'3.14',stdin:''});assert.equal(editor.get().version,'3.14');
});
test('runner isolates closing script tags and uses the selected runtime',()=>{
  const context={window:{addEventListener(){},removeEventListener(){}},document,setTimeout:()=>1,clearTimeout(){}};vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/js/homework_python.js','utf8'),context);
  const root=new Element();const stop=context.window.HomeworkPython.start(root,{version:'3.12',stdin:'',code:'print("</script><script>bad</script>")'},()=>{});
  const frame=root.children[0],src=frame.srcdoc;
  assert.equal((src.match(/<script>/g)||[]).length,1);assert.equal(frame.sandbox,'allow-scripts');assert(src.includes('v0.27.7/full/'));
  new vm.Script(src.slice(src.indexOf('<script>')+8,src.lastIndexOf('</script>')));
  stop();assert.equal(frame.removed,true);
});
