/* Titans Windows CRM — interface behaviour.
   Theme switch, sidebar drawer, and the small touches that make the screens
   feel alive: pointer spotlight on cards, counting numbers, click ripples and
   reveal-on-scroll. Everything degrades to a plain working page if it fails. */
(function () {
  "use strict";

  var root = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------- theme flip */
  function setTheme(name) {
    root.setAttribute("data-bs-theme", name);
    try { localStorage.setItem("tw-theme", name); } catch (e) { /* private mode */ }
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("#tw-theme-toggle");
    if (!toggle) return;
    event.preventDefault();
    setTheme(root.getAttribute("data-bs-theme") === "light" ? "dark" : "light");
  });

  /* ------------------------------------------------------ sidebar drawer */
  document.addEventListener("click", function (event) {
    if (event.target.closest("#tw-sidebar-toggle")) {
      document.body.classList.toggle("sidebar-open");
    } else if (event.target.closest("#tw-sidebar-backdrop")) {
      document.body.classList.remove("sidebar-open");
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") document.body.classList.remove("sidebar-open");
  });

  /* ------------------------------------------- pointer spotlight on cards */
  if (!reduced) {
    document.addEventListener("pointermove", function (event) {
      var card = event.target.closest(".card");
      if (!card) return;
      var box = card.getBoundingClientRect();
      card.style.setProperty("--mx", (event.clientX - box.left) + "px");
      card.style.setProperty("--my", (event.clientY - box.top) + "px");
    }, { passive: true });
  }

  /* ------------------------------------------------------- click ripples */
  if (!reduced) {
    document.addEventListener("pointerdown", function (event) {
      var button = event.target.closest(".btn");
      if (!button) return;
      var box = button.getBoundingClientRect();
      var size = Math.max(box.width, box.height);
      var ripple = document.createElement("span");
      ripple.className = "tw-ripple";
      ripple.style.width = ripple.style.height = size + "px";
      ripple.style.left = (event.clientX - box.left - size / 2) + "px";
      ripple.style.top = (event.clientY - box.top - size / 2) + "px";
      button.appendChild(ripple);
      setTimeout(function () { ripple.remove(); }, 600);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    /* ------------------------------------------------- numbers count up */
    var numbers = document.querySelectorAll(".stat-value, .tw-stat-value");
    numbers.forEach(function (node) {
      var text = node.textContent.trim();
      // Only plain integers animate; anything with currency or units is left alone.
      if (!/^\d{1,6}$/.test(text)) return;
      var target = parseInt(text, 10);
      if (reduced || target === 0) return;

      var started = false;
      var run = function () {
        if (started) return;
        started = true;
        var began = performance.now();
        var span = Math.min(200 + target * 12, 900);
        var tick = function (now) {
          var progress = Math.min((now - began) / span, 1);
          // ease-out, so it decelerates into the final number
          node.textContent = Math.round(target * (1 - Math.pow(1 - progress, 3)));
          if (progress < 1) requestAnimationFrame(tick);
        };
        node.textContent = "0";
        requestAnimationFrame(tick);
      };

      if ("IntersectionObserver" in window) {
        var watcher = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) { run(); watcher.disconnect(); }
          });
        }, { threshold: .4 });
        watcher.observe(node);
      } else {
        run();
      }
    });

    /* --------------------------------------------- reveal cards on scroll */
    if (!reduced && "IntersectionObserver" in window) {
      var panels = document.querySelectorAll(".tw-page .card:not(.stat-card)");
      if (panels.length) {
        var reveal = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("tw-in");
            reveal.unobserve(entry.target);
          });
        }, { threshold: .08, rootMargin: "0px 0px -40px 0px" });

        panels.forEach(function (panel, index) {
          panel.classList.add("tw-reveal");
          panel.style.animationDelay = Math.min(index, 6) * 45 + "ms";
          reveal.observe(panel);
        });

        // Failsafe: nothing stays invisible, whatever the observer does.
        setTimeout(function () {
          panels.forEach(function (panel) { panel.classList.add("tw-in"); });
        }, 1200);
      }
    }

    /* ------------------------------------- stat cards stagger in on load */
    document.querySelectorAll(".stat-card").forEach(function (card, index) {
      card.style.animation = "tw-fade-up .45s cubic-bezier(.22,1,.36,1) both";
      card.style.animationDelay = Math.min(index, 8) * 55 + "ms";
    });

    /* ------------------------------------------- flash messages step away */
    document.querySelectorAll(".tw-page > .alert-dismissible").forEach(function (alert) {
      setTimeout(function () {
        if (window.bootstrap && bootstrap.Alert) bootstrap.Alert.getOrCreateInstance(alert).close();
      }, 7000);
    });

    /* --------------------------------------------------- the bell reacts */
    var bell = document.querySelector(".tw-icon-btn .fa-bell, .tw-icon-btn .fa-regular.fa-bell");
    var badge = document.getElementById("tw-bell-badge");
    if (bell && badge && !reduced) {
      var button = bell.closest(".tw-icon-btn");
      setTimeout(function () { button.classList.add("tw-bell-pulse"); }, 600);
      setTimeout(function () { button.classList.remove("tw-bell-pulse"); }, 1400);
    }
  });
})();
