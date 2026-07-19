/**
 * motion.js — luxury physical-diary motion layer
 * ------------------------------------------------
 * Purely additive companion to app.js. Handles the three things
 * that need JS rather than CSS alone:
 *   1. Ambient floating dust motes (decorative, skipped on small
 *      screens / reduced motion)
 *   2. Scroll-triggered reveal for elements marked `.reveal`
 *   3. Animating server-rendered bar-chart fills from 0 on first
 *      paint, since their target width arrives as an inline style
 *
 * Does not touch any element IDs/classes that app.js already owns
 * (sidebar, theme, mood pills, autosave, uploads, etc.).
 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initMotes() {
    if (reduceMotion || window.innerWidth < 640) return;
    var host = document.getElementById("ambientMotes");
    if (!host) return;
    var COUNT = 9;
    for (var i = 0; i < COUNT; i++) {
      var m = document.createElement("span");
      m.className = "mote";
      var size = 3 + Math.random() * 4;
      m.style.left = (Math.random() * 100) + "vw";
      m.style.width = size + "px";
      m.style.height = size + "px";
      m.style.setProperty("--drift", (Math.random() * 60 - 30) + "px");
      m.style.animationDuration = (18 + Math.random() * 16) + "s";
      m.style.animationDelay = (Math.random() * -30) + "s";
      host.appendChild(m);
    }
  }

  function initReveal() {
    var targets = document.querySelectorAll(".reveal");
    if (!targets.length) return;
    if (reduceMotion || !("IntersectionObserver" in window)) {
      targets.forEach(function (el) { el.classList.add("is-visible"); });
      return;
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );
    targets.forEach(function (el) { io.observe(el); });
  }

  function initBarFills() {
    if (reduceMotion) return;
    var bars = document.querySelectorAll(".mood-bar-fill[style*='width']");
    if (!bars.length) return;
    bars.forEach(function (el) {
      var target = el.style.width;
      if (!target) return;
      el.style.width = "0%";
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (!el.style.transition) {
            el.style.transition = "width 1s cubic-bezier(0.22,1,0.36,1)";
          }
          el.style.width = target;
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initMotes();
    initReveal();
    initBarFills();
  });
})();
