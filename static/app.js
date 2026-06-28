// Model Risk Studio — light client-side interactivity (no framework).

document.addEventListener("DOMContentLoaded", () => {
  setupLiveTiering();
  setupRunOverlay();
});

// ── Live tier recalculation on the model detail page ──────────────────────────
function setupLiveTiering() {
  const panel = document.getElementById("tier-preview");
  const form = document.getElementById("ratings-form");
  if (!panel || !form) return;

  const family = panel.dataset.family || "Traditional ML";
  const inputs = form.querySelectorAll(".rating-input");

  inputs.forEach((el) => el.addEventListener("change", recalc));

  async function recalc() {
    const ratings = {};
    inputs.forEach((el) => { ratings[el.dataset.dim] = parseInt(el.value, 10); });

    try {
      const res = await fetch("/api/tiering/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ family, ratings }),
      });
      if (!res.ok) return;
      const data = await res.json();
      applyPreview(data);
    } catch (e) {
      /* offline / non-critical — leave the saved values shown */
    }
  }

  function applyPreview(data) {
    const badge = document.getElementById("tier-badge");
    if (badge) {
      badge.className = "badge tier-" + data.tier;
      badge.textContent = data.tier_label;
    }
    setText("tier-score", data.score);
    setText("tier-frequency", data.frequency_label);

    const flag = document.getElementById("preview-flag");
    if (flag) flag.textContent = "(unsaved preview — press Save to keep)";

    const esc = document.getElementById("tier-escalations");
    if (esc) {
      if (data.escalations && data.escalations.length) {
        esc.innerHTML = '<div class="esc-title">Escalation rules applied:</div><ul>' +
          data.escalations.map((e) => "<li>" + escapeHtml(e) + "</li>").join("") + "</ul>";
      } else {
        esc.innerHTML = "";
      }
    }

    (data.contributions || []).forEach((c) => {
      const lt = document.querySelector('[data-leveltext="' + c.key + '"]');
      if (lt) lt.textContent = c.level_text;
      const wt = document.querySelector('[data-weighted="' + c.key + '"]');
      if (wt) wt.textContent = c.weighted;
    });
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }
}

// ── "Running tests…" overlay on Track B ───────────────────────────────────────
function setupRunOverlay() {
  const runBtn = document.getElementById("run-btn");
  const overlay = document.getElementById("run-overlay");
  if (!runBtn || !overlay) return;
  runBtn.addEventListener("click", () => {
    // Let the form submit proceed; just show the overlay.
    setTimeout(() => overlay.classList.add("show"), 0);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
