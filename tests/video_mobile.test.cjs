const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('accounts/templates/accounts/lessons/video_lesson.html', 'utf8');
const helper = fs.readFileSync('static/js/video_presence.js', 'utf8');
function extract(name) {
    const start = template.indexOf('function ' + name + '(');
    assert(start >= 0);
    return template.slice(start, template.indexOf('\n}', start) + 2);
}
const window = {matchMedia: () => ({matches: true})};
vm.runInNewContext(helper, {window, document: {}, Math});
assert.equal(window.videoNeedsNativeControls(), true);
window.matchMedia = () => ({matches: false});
assert.equal(window.videoNeedsNativeControls(), false);
let focusCalls = 0;
window.focusVideoControl({focus(options) {focusCalls++; if (options) throw Error('old Safari');}});
assert.equal(focusCalls, 2, 'Unsupported focus options must not abort dialog event binding');

let created = 0;
vm.runInNewContext(extract('addVideoGuard') + '\naddVideoGuard();', {
    nativeTouchControls: true,
    document: {getElementById: id => id === 'videoBox' ? {} : null,
               createElement() {created++; throw Error('Touch player must not be covered');}},
});
assert.equal(created, 0);

(async () => {
    const timers = [];
    let exits = 0;
    const box = {};
    const context = {
        presencePrompting: false, serverCanComplete: false,
        presenceFullscreenExitPending: false, presenceRestoreFullscreen: false,
        document: {hidden: false, getElementById: () => box, fullscreenElement: {},
                   exitFullscreen() {exits++; return Promise.reject(Error('mobile exit rejected'));}},
        setTimeout(fn) {timers.push(fn);}, Promise,
    };
    vm.createContext(context);
    vm.runInContext(extract('showPresencePrompt'), context);
    context.showPresencePrompt({token: 'test'});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(exits, 1);
    assert.equal(timers.length, 1, 'Rejected fullscreen exit must yield rather than loop');
    let retried = false;
    context.showPresencePrompt = (challenge, attempted) => {
        assert.equal(challenge.token, 'test');
        assert.equal(attempted, true);
        retried = true;
    };
    timers[0]();
    assert(retried);
    console.log('PASS: native touch controls, Safari focus fallback, rejected fullscreen exit without recursion.');
})().catch(error => {console.error(error); process.exitCode = 1;});
