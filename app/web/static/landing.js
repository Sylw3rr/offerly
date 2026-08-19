// Offerly — the landing page's motion. No dependencies, nothing fetched.
//
// Everything here is decoration: with the script blocked the page is complete,
// only still. That is why elements are revealed by adding a class rather than
// being hidden in the markup — a hidden section that never un-hides is a page
// that appears broken.
(function () {
  "use strict";

  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ── Arriving into view ───────────────────────────────────────────
  var revealed = document.querySelectorAll("[data-reveal]");
  if (still || !("IntersectionObserver" in window)) {
    revealed.forEach(function (node) { node.classList.add("seen"); });
  } else {
    var watcher = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var index = [].indexOf.call(revealed, entry.target);
          entry.target.style.transitionDelay = (index % 6) * 55 + "ms";
          entry.target.classList.add("seen");
          watcher.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -12% 0px" },
    );
    revealed.forEach(function (node) { watcher.observe(node); });
  }

  // ── Bars, which fill once they are on screen ─────────────────────
  var bars = document.querySelectorAll("[data-bar]");
  function fill(bar) { bar.style.width = bar.getAttribute("data-bar") + "%"; }

  if (still || !("IntersectionObserver" in window)) {
    bars.forEach(fill);
  } else {
    var barWatcher = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          fill(entry.target);
          barWatcher.unobserve(entry.target);
        });
      },
      { threshold: 0.3 },
    );
    bars.forEach(function (bar) { barWatcher.observe(bar); });
  }

  if (still) return; // Nothing below this line is worth its listeners.

  // ── The loop section: which step you are looking at ──────────────
  var steps = [].slice.call(document.querySelectorAll("[data-step]"));
  var stepNumber = document.querySelector("[data-step-num]");
  var stepFill = document.querySelector("[data-step-fill]");

  function trackSteps() {
    if (!steps.length || !stepFill) return;
    var view = window.innerHeight;
    var first = steps[0].getBoundingClientRect();
    var last = steps[steps.length - 1].getBoundingClientRect();
    var span = last.bottom - first.top;
    var progress = span > 0 ? (view * 0.62 - first.top) / span : 0;
    progress = Math.min(1, Math.max(0, progress));
    stepFill.style.width = progress * 100 + "%";

    var active = 0;
    steps.forEach(function (step, index) {
      if (step.getBoundingClientRect().top < view * 0.66) active = index;
    });
    steps.forEach(function (step, index) {
      step.classList.toggle("on", index === active);
      step.classList.toggle("far", index > active + 1);
    });
    if (stepNumber) stepNumber.textContent = "0" + (active + 1);
  }

  // ── Parallax, and the backdrop drifting with the page ────────────
  var PARALLAX_LIMIT = 10;
  var floating = [].slice.call(document.querySelectorAll("[data-parallax]"));
  var backdrop = document.querySelector("[data-bg]");
  var pointerX = 0;
  var pointerY = 0;

  function onScroll() {
    var y = window.scrollY;
    floating.forEach(function (node) {
      var rate = parseFloat(node.getAttribute("data-parallax")) || 0;
      // Clamped: the cards sit in a grid with a 22px gap, and an unbounded
      // drift pulls neighbours through each other a few hundred pixels down
      // the page. Depth is the point; collision is not.
      var offset = Math.max(-PARALLAX_LIMIT, Math.min(PARALLAX_LIMIT, -y * rate));
      node.style.transform = "translate3d(0," + offset + "px,0)";
    });
    if (backdrop) {
      backdrop.style.transform =
        "translate3d(" + pointerX + "px," + (pointerY - Math.min(120, y * 0.045)) + "px,0)";
    }
    trackSteps();
  }

  var waiting = false;
  function schedule() {
    if (waiting) return;
    waiting = true;
    requestAnimationFrame(function () {
      waiting = false;
      onScroll();
    });
  }

  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);

  // ── The backdrop leans towards the cursor ────────────────────────
  window.addEventListener(
    "mousemove",
    function (event) {
      pointerX = (event.clientX / window.innerWidth - 0.5) * 52;
      pointerY = (event.clientY / window.innerHeight - 0.5) * 40;
      schedule();
    },
    { passive: true },
  );

  // ── Buttons that lean back ───────────────────────────────────────
  var magnets = [].slice.call(document.querySelectorAll("[data-magnetic]"));
  window.addEventListener(
    "mousemove",
    function (event) {
      magnets.forEach(function (button) {
        var box = button.getBoundingClientRect();
        var dx = event.clientX - (box.left + box.width / 2);
        var dy = event.clientY - (box.top + box.height / 2);
        var distance = Math.hypot(dx, dy);
        if (distance > 150) {
          button.style.transform = "";
          return;
        }
        var pull = (1 - distance / 150) * 0.28;
        button.style.transform = "translate(" + dx * pull + "px," + dy * pull + "px)";
      });
    },
    { passive: true },
  );

  onScroll();
})();
