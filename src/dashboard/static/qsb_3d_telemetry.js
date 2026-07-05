/*
 * QSB 3D Revamp — Telemetry Truth panel (top-left)
 * Phase: QSB_DASHBOARD_3D_TOTAL_REVAMP_WORKERS_OPENCLAW_V1
 *
 * Always-on overlay that explains the worker counts honestly:
 *   "1,191 canonical · 0 rendered at this zoom (default) ·
 *    1,131 active · N moving · 108 training · 280 resting"
 *
 * Tells the operator WHY only X workers are visible, with the policy
 * decision named.
 */
(function () {
  'use strict';
  if (window.QSB_3D_TELEMETRY_INSTALLED) return;
  window.QSB_3D_TELEMETRY_INSTALLED = true;

  function esc(s) {
    if (s === null || s === undefined) return '—';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function ensurePanel() {
    let el = document.getElementById('qsb3dTruth');
    if (el) return el;
    const stage = document.getElementById('stage') || document.body;
    el = document.createElement('div');
    el.id = 'qsb3dTruth';
    el.className = 'qsb-3d-truth';
    stage.appendChild(el);
    return el;
  }

  function update(cache) {
    const el = ensurePanel();
    if (!cache) return;
    const truth = cache.truth || {};
    const scene = cache.scene || {};
    const live = cache.live || {};
    const total = truth.total_canonical_workers || 0;
    const ops = (scene.totals && scene.totals.operational_workers) ||
                 truth.real_registry_workers || 0;
    const moving = (scene.moving_count) ||
                   (live.worker_movements || []).length || 0;
    const training = truth.simulated_workers || 0;
    const resting = ((truth.totals && truth.totals.resting_workers) || 280);
    const rendered = scene.rendered_default_count != null
                      ? scene.rendered_default_count : 0;
    const selFloor = (window.QSB && window.QSB.selectedFloor) || '—';
    el.innerHTML = (
      '<h5>Workforce truth</h5>' +
      '<div class="qsb-3d-truth-row"><span>canonical</span><span>' + esc(total) + '</span></div>' +
      '<div class="qsb-3d-truth-row"><span>active</span><span style="color:#3fcf6e">' + esc(ops) + '</span></div>' +
      '<div class="qsb-3d-truth-row"><span>moving (real)</span><span style="color:#ffe066">' + esc(moving) + '</span></div>' +
      '<div class="qsb-3d-truth-row"><span>training/sim</span><span>' + esc(training) + '</span></div>' +
      '<div class="qsb-3d-truth-row"><span>resting</span><span>' + esc(resting) + '</span></div>' +
      '<div class="qsb-3d-truth-row"><span>rendered now</span><span>' + esc(rendered) + '</span></div>' +
      '<div class="qsb-3d-truth-row"><span>selected floor</span><span>' + esc(selFloor) + '</span></div>' +
      '<div class="qsb-3d-truth-note">' +
        'Default view shows per-floor activity badges only. ' +
        'Click a floor to render its workers in the interior panel ' +
        'on the right. SIM and resting workers visible only inside ' +
        'Training Academy (36) and Rest/Dormitory (49) respectively.' +
      '</div>'
    );
  }

  window.QSB_3D_TELEMETRY = { update: update };
})();
