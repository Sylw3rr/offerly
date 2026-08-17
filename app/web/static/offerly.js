// Offerly — the interactivity, with no dependencies and nothing fetched.
//
// The handoff package leaned on HTMX for the palette and the registry search.
// Both work as plain HTML here instead: the palette filters a static list it
// already has, and search is a form that submits. Less to load, and it still
// works with scripting off.
(function () {
  "use strict";

  // ── Command palette (⌘K / Ctrl+K) ────────────────────────────────
  var palette = document.getElementById("palette");

  function openPalette() {
    if (!palette) return;
    palette.hidden = false;
    var input = palette.querySelector("input");
    if (input) { input.value = ""; input.focus(); }
    filterPalette("");
  }

  function closePalette() {
    if (palette) palette.hidden = true;
  }

  function filterPalette(query) {
    if (!palette) return;
    palette.querySelectorAll(".palette-item").forEach(function (item) {
      item.hidden = query !== "" && item.textContent.toLowerCase().indexOf(query) === -1;
    });
  }

  document.querySelectorAll("[data-palette-open]").forEach(function (button) {
    button.addEventListener("click", openPalette);
  });

  if (palette) {
    palette.addEventListener("click", function (event) {
      if (event.target === palette) closePalette();
    });
    var paletteInput = palette.querySelector("input");
    if (paletteInput) {
      paletteInput.addEventListener("input", function () {
        filterPalette(paletteInput.value.toLowerCase());
      });
    }
  }

  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openPalette();
    }
    if (event.key === "Escape") { closePalette(); closeDialogs(); }
  });

  // ── Confirmation dialogs ─────────────────────────────────────────
  // Any form carrying data-confirm-title asks before it goes through. The
  // fallback when scripting is off is the form simply submitting, so every
  // destructive form still states its consequence on the page itself.
  function closeDialogs() {
    document.querySelectorAll(".dialog-backdrop[data-runtime]").forEach(function (node) {
      node.remove();
    });
  }

  document.querySelectorAll("form[data-confirm-title]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.confirmed) return;
      event.preventDefault();

      var backdrop = document.createElement("div");
      backdrop.className = "dialog-backdrop";
      backdrop.dataset.runtime = "1";
      backdrop.innerHTML =
        '<div class="dialog" role="dialog" aria-modal="true">' +
        '<span class="dialog-title"></span><p class="dialog-body"></p>' +
        '<div class="dialog-actions">' +
        '<button class="btn btn-secondary" type="button" data-cancel></button>' +
        '<button class="btn btn-primary" type="button" data-ok></button>' +
        "</div></div>";

      backdrop.querySelector(".dialog-title").textContent = form.dataset.confirmTitle;
      backdrop.querySelector(".dialog-body").textContent = form.dataset.confirmBody || "";
      backdrop.querySelector("[data-cancel]").textContent = form.dataset.confirmCancel || "Cancel";
      backdrop.querySelector("[data-ok]").textContent = form.dataset.confirmOk || "Confirm";

      backdrop.querySelector("[data-cancel]").addEventListener("click", function () {
        backdrop.remove();
      });
      backdrop.querySelector("[data-ok]").addEventListener("click", function () {
        form.dataset.confirmed = "1";
        form.submit();
      });

      document.body.appendChild(backdrop);
      backdrop.querySelector("[data-cancel]").focus();
    });
  });

  // ── Copy to clipboard ────────────────────────────────────────────
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var node = document.getElementById(button.dataset.copy);
      if (!node) return;
      var text = node.textContent.trim();

      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () {
          toast(button.dataset.copyDone || "Copied");
        });
      } else {
        // The clipboard API needs a secure context; select the text so Ctrl+C
        // still does the job.
        var range = document.createRange();
        range.selectNodeContents(node);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
    });
  });

  // ── Toast ────────────────────────────────────────────────────────
  var toastTimer;

  function toast(text) {
    var host = document.querySelector(".toast");
    if (!host) {
      host = document.createElement("div");
      host.className = "toast";
      host.setAttribute("role", "status");
      host.innerHTML = '<div class="card"><span></span></div>';
      document.body.appendChild(host);
    }
    host.querySelector("span").textContent = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { host.remove(); }, 4200);
  }

  window.offerlyToast = toast;

  // ── Suggested answer labels ──────────────────────────────────────
  document.querySelectorAll("[data-fill]").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = document.getElementById(button.dataset.fill);
      if (!target) return;
      target.value = button.textContent.trim();
      var next = document.getElementById(button.dataset.fillNext);
      if (next) next.focus();
    });
  });
})();
