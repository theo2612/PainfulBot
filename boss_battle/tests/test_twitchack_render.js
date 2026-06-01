/* Regression test for the TwitcHack player-panel render path.
 *
 * Defends the two fixes made after an auto-attack script (CypherEnigma,
 * 2026-05-31) flooded the bot with attack commands and made the web GUI hard
 * to click. The bot emits one players_update per command; on the old code each
 * push ran a synchronous full renderPlayers AND unconditionally re-appended
 * every card, pinning the main thread and yanking cards out from under the
 * pointer mid-click.
 *
 *   1. render coalescing  — a burst of schedule() calls within a single
 *      animation frame must collapse to ONE render (the latest payload), not
 *      one render per push.
 *   2. conditional reorder — when the card order is unchanged, needsReorder()
 *      must return false so the render path skips the card re-append churn.
 *
 * Pure logic, no DOM, no dependencies. Run from boss_battle/:
 *     node tests/test_twitchack_render.js
 */

'use strict';

const assert = require('assert');
const path = require('path');
const { makeCoalescer, needsReorder } =
  require(path.join(__dirname, '..', 'static', 'twitchack_render.js'));

let failures = 0;
function test(name, fn) {
  try {
    fn();
    console.log('  ok   ' + name);
  } catch (e) {
    failures++;
    console.log('  FAIL ' + name + '\n       ' + e.message);
  }
}

// ── 1. Render coalescing ────────────────────────────────────────────────────

test('a burst within one frame collapses to a single render', () => {
  let frameCb = null;
  const raf = (cb) => { frameCb = cb; };   // capture; firing it = one frame
  const rendered = [];
  const schedule = makeCoalescer(raf, (p) => rendered.push(p));

  for (let i = 0; i < 50; i++) schedule({ tick: i });
  assert.strictEqual(rendered.length, 0, 'nothing renders before the frame fires');

  frameCb();                                // the one animation frame
  assert.strictEqual(rendered.length, 1, 'exactly one render for the whole burst');
  assert.deepStrictEqual(rendered[0], { tick: 49 }, 'renders the most recent payload');
});

test('each new frame renders again so steady-state still updates', () => {
  let frameCb = null;
  const raf = (cb) => { frameCb = cb; };
  const rendered = [];
  const schedule = makeCoalescer(raf, (p) => rendered.push(p));

  schedule('a'); schedule('b');
  frameCb();
  schedule('c');
  frameCb();
  assert.deepStrictEqual(rendered, ['b', 'c']);
});

test('a quiet frame (no schedule) renders nothing', () => {
  let frameCb = null;
  const raf = (cb) => { frameCb = cb; };
  const rendered = [];
  const schedule = makeCoalescer(raf, (p) => rendered.push(p));

  schedule('x');
  frameCb();                                // renders 'x'
  if (frameCb) frameCb();                   // a stray extra frame, no new schedule
  assert.deepStrictEqual(rendered, ['x'], 'no phantom re-render without a new push');
});

// ── 2. Conditional reorder ──────────────────────────────────────────────────

test('identical order needs no reorder', () => {
  assert.strictEqual(needsReorder(['a', 'b', 'c'], ['a', 'b', 'c']), false);
});

test('changed order needs reorder', () => {
  assert.strictEqual(needsReorder(['b', 'a', 'c'], ['a', 'b', 'c']), true);
});

test('a joined or departed player needs reorder', () => {
  assert.strictEqual(needsReorder(['a', 'b'], ['a', 'b', 'c']), true);
  assert.strictEqual(needsReorder(['a', 'b', 'c'], ['a', 'b']), true);
});

test('empty lists need no reorder', () => {
  assert.strictEqual(needsReorder([], []), false);
});

// ── Summary ─────────────────────────────────────────────────────────────────

if (failures) {
  console.error('\n' + failures + ' test(s) failed');
  process.exit(1);
}
console.log('\nall tests passed');
