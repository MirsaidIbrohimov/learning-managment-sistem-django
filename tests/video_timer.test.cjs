const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('accounts/templates/accounts/lessons/video_lesson.html', 'utf8');
function extract(name) {
    const start = template.indexOf('function ' + name + '(');
    assert(start >= 0, name);
    return template.slice(start, template.indexOf('\n}', start) + 2);
}

// The countdown must not use a wall clock: it is the server-required time minus
// watchedTime, which only grows while the player position actually advances.
assert(!/playedClockSeconds|serverRemaining\b/.test(template), 'Wall-clock countdown must be removed');

const el = () => ({textContent: '', style: {}, classList: {add() {}, remove() {}}});
const context = {
    isReady: false, serverCanComplete: false, durationLocked: true,
    requiredTime: 100, totalSeconds: 110, watchedTime: 40,
    lastDisplayedRemaining: null, lastFinalizationRequestAt: 0, circumference: 100,
    countdownEl: el(), ringFill: el(), timerLabel: el(), statusText: el(),
    watchedDurationText: el(), watchedPercentageText: el(),
    formatTime(s) { s = Math.max(0, Math.round(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; },
    sendBeat() { context.beats++; }, beats: 0, Date, Math,
};
vm.createContext(context);
vm.runInContext(extract('updateTimerUI'), context);
const show = watched => { context.watchedTime = watched; context.updateTimerUI(); return context.countdownEl.textContent; };

assert.equal(show(40), '1:00');
assert.equal(show(41), '0:59');
assert.equal(show(41), '0:59', 'Paused/buffering player must not move the countdown');
// Server credited less than the local estimate: show the truth instead of
// holding a too-low value until the server catches up (the old freeze).
assert.equal(show(35), '1:05');
assert.equal(show(36), '1:04', 'Countdown keeps moving after a server correction');
// A sub-second correction from network latency does not flicker backwards.
assert.equal(show(36.5), '1:04');
assert.equal(show(35.8), '1:04');
assert.equal(show(99.5), '0:01');
assert.equal(show(100), '0:00');
assert.equal(context.timerLabel.textContent, 'Tekshirilmoqda');
assert(context.beats >= 1, 'Finalization beat is requested at the end');
console.log('PASS: countdown follows real playback, corrects to server, never freezes ahead of it.');
