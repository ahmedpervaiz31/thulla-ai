/** Table page HTML shell. */

export const TABLE_TEMPLATE = `
<main class="table" data-page="table">
  <aside class="ideal-pad hidden" data-role="ideal-pad" aria-label="Ideal move coach">
    <button
      type="button"
      class="ideal-handle"
      data-role="ideal-toggle"
      aria-expanded="false"
      aria-controls="ideal-panel"
      title="Open ideal move"
    ></button>
    <div class="ideal-panel" id="ideal-panel" data-role="ideal-panel">
      <div class="ideal-head">
        <span class="ideal-title">IDEAL MOVE</span>
        <span class="ideal-sub">BOT MODEL</span>
      </div>
      <div class="ideal-body" data-role="ideal-body"></div>
    </div>
  </aside>

  <div class="table-shell" data-role="table-shell">
    <div class="arena" data-role="arena">
      <div class="seat seat-top" data-slot="top"></div>
      <div class="seat seat-left" data-slot="left"></div>
      <div class="center-zone">
        <div class="event-banner" data-role="event-banner"></div>
        <div class="trick-box" data-role="trick-box">
          <div class="trick-meta">
            <span data-role="lead-label">LEAD: —</span>
            <span data-role="pot-label">POT: 0</span>
          </div>
          <div class="trick-cards" data-role="trick-cards"></div>
        </div>
        <p class="rule-hint" data-role="rule-hint"></p>
      </div>
      <div class="seat seat-right" data-slot="right"></div>
      <div class="seat seat-bottom" data-slot="bottom"></div>
    </div>

    <div class="hand-zone" data-role="hand-zone">
      <div class="you-rail hidden" data-role="you-rail">
        <div class="you-bar">
          <span class="you-bar-name" data-role="you-name">YOU</span>
          <span class="you-bar-meta" data-role="you-meta">0 CARDS</span>
          <span class="you-bar-turn">TURN</span>
        </div>
        <div class="hand" data-role="hand"></div>
      </div>
    </div>

    <div class="take-modal hidden" data-role="take-modal">
      <p data-role="take-text">Take neighbor's cards?</p>
      <div class="take-actions">
        <button type="button" class="action-btn yes" data-role="take-yes">YES</button>
        <button type="button" class="action-btn no" data-role="take-no">NO</button>
      </div>
    </div>

    <div class="finish-modal hidden" data-role="finish-modal">
      <h2>GAME OVER</h2>
      <ol data-role="finish-list"></ol>
      <div class="finish-actions">
        <button type="button" class="start-btn" data-role="review-btn">▶ REVIEW MOVES</button>
        <button type="button" class="start-btn secondary" data-role="again-btn">◀ BACK TO LOBBY</button>
      </div>
    </div>

    <footer class="controls" data-role="controls">
      <div class="ctrl-left">
        <button type="button" class="chip" data-role="sort-suit">SUIT</button>
        <button type="button" class="chip" data-role="sort-rank">RANK</button>
      </div>
      <div class="ctrl-center">
        <button type="button" class="play-btn" data-role="play-btn" disabled>▶ PLAY SELECTED</button>
        <button type="button" class="play-btn secondary hidden" data-role="step-btn">▶ NEXT STEP</button>
        <button type="button" class="chip hidden" data-role="auto-btn">AUTO</button>
      </div>
      <div class="ctrl-right">
        <span class="status" data-role="status-text">STATUS: —</span>
      </div>
    </footer>
  </div>

  <div class="review-nav hidden" data-role="review-nav" aria-label="Review turn navigation">
    <button type="button" class="review-btn lobby" data-role="review-lobby" title="Back to lobby">LOBBY</button>
    <button type="button" class="review-btn" data-role="review-prev" title="Previous turn (←)">◀</button>
    <span class="review-label" data-role="review-label">1 / 1</span>
    <button type="button" class="review-btn" data-role="review-next" title="Next turn (→)">▶</button>
  </div>

  <div class="hand-peek hidden" data-role="hand-peek" aria-hidden="true">
    <div class="hand-peek-backdrop" data-role="hand-peek-close"></div>
    <div class="hand-peek-panel" role="dialog" aria-labelledby="hand-peek-title">
      <div class="hand-peek-head">
        <div>
          <h2 class="hand-peek-title" id="hand-peek-title" data-role="hand-peek-title">HAND</h2>
          <p class="hand-peek-meta" data-role="hand-peek-meta"></p>
        </div>
        <button type="button" class="hand-peek-close" data-role="hand-peek-close" aria-label="Close">✕</button>
      </div>
      <div class="hand-peek-body" data-role="hand-peek-body"></div>
    </div>
  </div>

  <aside class="scratch-pad" data-role="scratch-pad" aria-label="Public intel scratch pad">
    <button
      type="button"
      class="scratch-handle"
      data-role="scratch-toggle"
      aria-expanded="false"
      aria-controls="scratch-panel"
      title="Open scratch pad"
    ></button>
    <div class="scratch-panel" id="scratch-panel" data-role="scratch-panel">
      <div class="scratch-head">
        <span class="scratch-title">SCRATCH PAD</span>
        <span class="scratch-sub">PUBLIC INFO</span>
      </div>
      <div class="scratch-body" data-role="scratch-body"></div>
    </div>
  </aside>
</main>
`;
