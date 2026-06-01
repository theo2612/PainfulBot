/* Pure, DOM-free helpers for the TwitcHack player-panel render path.
 *
 * Pulled out of the inline page script so the two pieces of logic that fixed
 * the "hard to click during a command flood" problem can be unit-tested in
 * Node without a browser (see tests/test_twitchack_render.js). Loaded as a
 * plain <script> before the inline page script, and also require()-able as a
 * CommonJS module from the test.
 */
(function (root) {
  'use strict';

  /* Decide whether the player-card DOM actually needs re-ordering. Returns
   * true only when `current` differs from `desired` (same length AND same
   * sequence => false). This is what stops the render path from detaching and
   * re-appending every card on every push — the DOM churn that yanked cards
   * out from under the pointer mid-click during a command flood. */
  function needsReorder(desired, current) {
    if (desired.length !== current.length) return true;
    for (var i = 0; i < desired.length; i++) {
      if (desired[i] !== current[i]) return true;
    }
    return false;
  }

  /* Build a coalescer that collapses any number of schedule(payload) calls
   * within a single animation frame into ONE render(payload) call, using the
   * most recent payload. A command flood emits one players_update per command;
   * without this, each one forced a synchronous full re-render on every
   * viewer, pinning the main thread. No update is dropped — only the redundant
   * intermediate renders are. `raf` is injected (real requestAnimationFrame in
   * the page, a manual stepper in tests). */
  function makeCoalescer(raf, render) {
    var pending = null;
    var hasPending = false;
    var scheduled = false;
    function flush() {
      scheduled = false;
      if (!hasPending) return;
      var payload = pending;
      pending = null;
      hasPending = false;
      render(payload);
    }
    return function schedule(payload) {
      pending = payload;
      hasPending = true;
      if (scheduled) return;
      scheduled = true;
      raf(flush);
    };
  }

  var api = { needsReorder: needsReorder, makeCoalescer: makeCoalescer };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.TwitcHackRender = api;
})(typeof window !== 'undefined' ? window : this);
