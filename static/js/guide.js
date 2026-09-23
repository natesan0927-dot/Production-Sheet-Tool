/* Titans Windows CRM — the walkthrough.

   Two pieces that share this file because they hand off to each other:

   1. The narrated intro. An avatar talks over a screenshot of whatever it is
      describing. The voice is the browser's own speech synthesis, which needs a
      click before it will start — hence the Play button on the poster. Where
      there is no voice (or it is muted) the scenes run on a timer instead and
      the script stays on screen, so nothing is lost.

   2. The guided tour. This one runs across page loads: the step index lives in
      localStorage, "Next" navigates to the next tab, and the step is drawn
      again once that page has loaded.

   Both are skippable, both record that they have been seen so they only happen
   once, and both can be replayed from the Guide tab. */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var TOUR_KEY = "tw-tour";
  var MUTE_KEY = "tw-guide-muted";

  function read(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try { return JSON.parse(node.textContent); } catch (e) { return null; }
  }

  function csrf() {
    var match = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return match ? match[2] : "";
  }

  function markSeen(what) {
    var url = (document.getElementById("tw-walkthrough") || {}).dataset;
    url = url && url.seenUrl;
    if (!url) return;
    var body = new FormData();
    body.append(what, "1");
    fetch(url, { method: "POST", body: body, headers: { "X-CSRFToken": csrf() } }).catch(function () {});
  }

  /* ===================================================================== */
  /*  1. the narrated intro                                                */
  /* ===================================================================== */

  var player = (function () {
    var root = document.getElementById("tw-walkthrough");
    var scenes = read("tw-wt-scenes");
    if (!root || !scenes || !scenes.length) return null;

    var shot = root.querySelector(".tw-wt-shot");
    var caption = root.querySelector(".tw-wt-caption");
    var script = root.querySelector(".tw-wt-script");
    var dots = root.querySelector(".tw-wt-dots");
    var avatar = root.querySelector(".tw-wt-stage .tw-wt-avatar");
    var startCover = root.querySelector('[data-wt-cover="start"]');
    var endCover = root.querySelector('[data-wt-cover="end"]');

    var index = -1;
    var timer = null;
    var playing = false;
    var muted = false;
    try { muted = localStorage.getItem(MUTE_KEY) === "1"; } catch (e) {}
    var canSpeak = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

    scenes.forEach(function (_scene, i) {
      var dot = document.createElement("button");
      dot.type = "button";
      dot.className = "tw-wt-dot";
      dot.setAttribute("aria-label", "Scene " + (i + 1));
      dot.addEventListener("click", function () { show(i); });
      dots.appendChild(dot);
    });

    function stopVoice() {
      if (canSpeak) { try { window.speechSynthesis.cancel(); } catch (e) {} }
      clearTimeout(timer);
      timer = null;
      avatar.classList.remove("is-speaking");
    }

    function voice() {
      // Prefer an English voice; otherwise let the browser choose for itself.
      var all = window.speechSynthesis.getVoices() || [];
      return all.filter(function (v) { return /^en(-|_|$)/i.test(v.lang); })[0] || null;
    }

    /* Roughly how long the line takes to read aloud, for when there is no voice. */
    function readingTime(text) {
      return Math.max(4200, (text.split(/\s+/).length / 2.7) * 1000);
    }

    function speak(scene) {
      avatar.classList.add("is-speaking");
      if (!canSpeak || muted) {
        timer = setTimeout(advance, readingTime(scene.narration));
        return;
      }
      var line = new SpeechSynthesisUtterance(scene.narration);
      var chosen = voice();
      if (chosen) line.voice = chosen;
      line.rate = 0.98;
      line.pitch = 1.02;
      line.onend = advance;
      // Some browsers drop an utterance silently; the timer is the safety net.
      timer = setTimeout(advance, readingTime(scene.narration) + 4000);
      try {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(line);
      } catch (e) {
        clearTimeout(timer);
        timer = setTimeout(advance, readingTime(scene.narration));
      }
    }

    function advance() {
      if (!playing) return;
      if (index >= scenes.length - 1) { finish(); return; }
      show(index + 1);
    }

    function show(i) {
      stopVoice();
      index = i;
      var scene = scenes[i];

      caption.textContent = scene.caption;
      script.textContent = scene.narration;

      var src = root.dataset.shots + scene.shot + ".jpg";
      shot.onerror = function () { shot.hidden = true; };
      shot.onload = function () { shot.hidden = false; };
      shot.classList.remove("is-in");
      shot.src = src;
      requestAnimationFrame(function () { shot.classList.add("is-in"); });

      Array.prototype.forEach.call(dots.children, function (dot, n) {
        dot.classList.toggle("is-on", n === i);
        dot.classList.toggle("is-done", n < i);
      });

      root.querySelector('[data-wt="back"]').disabled = i === 0;
      if (playing) speak(scene);
    }

    function open(autoplay) {
      root.hidden = false;
      document.body.classList.add("tw-wt-open");
      endCover.hidden = true;
      startCover.hidden = !!autoplay;
      if (autoplay) play(); else show(0);
    }

    function play() {
      playing = true;
      startCover.hidden = true;
      endCover.hidden = true;
      show(index < 0 || index >= scenes.length - 1 ? 0 : index);
    }

    function finish() {
      playing = false;
      stopVoice();
      endCover.hidden = false;
      markSeen("intro");
    }

    function close(alsoTour) {
      playing = false;
      stopVoice();
      root.hidden = true;
      document.body.classList.remove("tw-wt-open");
      markSeen("intro");
      if (alsoTour) markSeen("tour");
    }

    root.addEventListener("click", function (event) {
      var button = event.target.closest("[data-wt]");
      if (!button) return;
      var action = button.dataset.wt;

      if (action === "play" || action === "replay") { index = -1; play(); }
      else if (action === "next") { stopVoice(); if (index >= scenes.length - 1) finish(); else show(index + 1); }
      else if (action === "back") { stopVoice(); show(Math.max(0, index - 1)); }
      else if (action === "skip") { close(true); }
      else if (action === "close") { close(true); }
      else if (action === "tour") { close(false); tour.start(); }
      else if (action === "mute") {
        muted = !muted;
        try { localStorage.setItem(MUTE_KEY, muted ? "1" : "0"); } catch (e) {}
        root.classList.toggle("is-muted", muted);
        if (playing) { stopVoice(); speak(scenes[index]); }
      }
    });

    document.addEventListener("keydown", function (event) {
      if (root.hidden) return;
      if (event.key === "Escape") close(true);
      if (event.key === "ArrowRight") { stopVoice(); show(Math.min(scenes.length - 1, index + 1)); }
      if (event.key === "ArrowLeft") { stopVoice(); show(Math.max(0, index - 1)); }
    });

    root.classList.toggle("is-muted", muted);
    return { open: open };
  })();

  /* ===================================================================== */
  /*  2. the guided tour                                                   */
  /* ===================================================================== */

  var tour = (function () {
    var steps = read("tw-tour-steps") || [];
    var bubble = null;

    function state() {
      try { return JSON.parse(localStorage.getItem(TOUR_KEY)); } catch (e) { return null; }
    }
    function save(value) {
      try { localStorage.setItem(TOUR_KEY, JSON.stringify(value)); } catch (e) {}
    }
    function clear() {
      try { localStorage.removeItem(TOUR_KEY); } catch (e) {}
    }

    function target(step) {
      return document.querySelector('#tw-sidebar .nav-link[href="' + step.url + '"]');
    }

    function teardown() {
      document.querySelectorAll(".tw-tour-spot").forEach(function (node) {
        node.classList.remove("tw-tour-spot");
      });
      if (bubble) { bubble.remove(); bubble = null; }
      document.body.classList.remove("tw-tour-on");
    }

    function place(node, anchor) {
      var margin = 14;
      if (!anchor) {
        node.style.left = Math.max(margin, (window.innerWidth - node.offsetWidth) / 2) + "px";
        node.style.top = Math.max(margin, (window.innerHeight - node.offsetHeight) / 2) + "px";
        node.classList.add("is-centred");
        return;
      }
      var box = anchor.getBoundingClientRect();
      var left = box.right + 18;
      if (left + node.offsetWidth > window.innerWidth - margin) {
        left = Math.max(margin, window.innerWidth - node.offsetWidth - margin);
      }
      var top = box.top + box.height / 2 - node.offsetHeight / 2;
      top = Math.min(Math.max(margin, top), window.innerHeight - node.offsetHeight - margin);
      node.style.left = left + "px";
      node.style.top = top + "px";
    }

    function render(i) {
      teardown();
      var step = steps[i];
      if (!step) { stop(true); return; }

      document.body.classList.add("tw-tour-on");
      // On a phone the tabs live behind the drawer, so open it to show them.
      if (window.innerWidth < 992) document.body.classList.add("sidebar-open");

      var anchor = target(step);
      if (anchor) anchor.classList.add("tw-tour-spot");

      bubble = document.createElement("div");
      bubble.className = "tw-tour-bubble";
      bubble.innerHTML =
        '<div class="tw-tour-count">Step ' + (i + 1) + " of " + steps.length + "</div>" +
        "<strong></strong><p></p>" +
        '<div class="tw-tour-actions">' +
        '<button type="button" class="btn btn-sm btn-link px-0" data-tour="stop">Skip the tour</button>' +
        '<span class="flex-grow-1"></span>' +
        '<button type="button" class="btn btn-sm btn-outline-secondary" data-tour="back"' +
        (i === 0 ? " disabled" : "") + ">Back</button>" +
        '<button type="button" class="btn btn-sm btn-primary" data-tour="next">' +
        (i === steps.length - 1 ? "Finish" : "Next") + "</button></div>";
      bubble.querySelector("strong").textContent = step.title;
      bubble.querySelector("p").textContent = step.body;
      document.body.appendChild(bubble);

      place(bubble, anchor);
      requestAnimationFrame(function () { bubble.classList.add("is-in"); });

      bubble.addEventListener("click", function (event) {
        var button = event.target.closest("[data-tour]");
        if (!button) return;
        if (button.dataset.tour === "next") go(i + 1);
        else if (button.dataset.tour === "back") go(i - 1);
        else stop(true);
      });
    }

    function go(i) {
      if (i < 0) return;
      if (i >= steps.length) { stop(true); return; }
      var step = steps[i];
      if (step.url === window.location.pathname) {
        save({ i: i, tries: 0 });
        render(i);
        return;
      }
      save({ i: i, tries: 0 });
      window.location.href = step.url;
    }

    function stop(seen) {
      teardown();
      clear();
      if (seen) markSeen("tour");
    }

    function start() {
      if (!steps.length) return;
      go(0);
    }

    /* Pick the tour back up after a navigation. */
    function resume() {
      var current = state();
      if (!current || !steps.length) return;
      var i = Math.min(Math.max(0, current.i | 0), steps.length - 1);
      var step = steps[i];

      if (step.url !== window.location.pathname) {
        // Landed somewhere else — try once to get back, then give up rather
        // than bounce the person between pages.
        var tries = (current.tries | 0) + 1;
        if (tries > 1) { stop(false); return; }
        save({ i: i, tries: tries });
        window.location.href = step.url;
        return;
      }
      save({ i: i, tries: 0 });
      render(i);
    }

    window.addEventListener("resize", function () {
      var current = state();
      if (bubble && current) place(bubble, target(steps[current.i]));
    });

    document.addEventListener("keydown", function (event) {
      if (bubble && event.key === "Escape") stop(true);
    });

    return { start: start, resume: resume, steps: steps };
  })();

  /* ===================================================================== */

  document.addEventListener("DOMContentLoaded", function () {
    tour.resume();

    if (player && document.getElementById("tw-walkthrough").dataset.autostart) {
      // Let the page settle before it takes over the screen.
      setTimeout(function () { player.open(false); }, reduced ? 0 : 400);
    }

    document.addEventListener("click", function (event) {
      var button = event.target.closest("[data-guide]");
      if (!button) return;
      if (button.dataset.guide === "play" && player) player.open(false);
      if (button.dataset.guide === "tour") tour.start();
    });
  });
})();
