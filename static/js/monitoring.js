/* Titans Windows — Monitoring.
   Attendance: the overtime box and "mark the rest present". An employee's
   calendar: tap a day for its overtime. Today's Work: the phone's location,
   taken when the day starts and at every site stop. */
(function () {
  "use strict";

  /* ------------------------------------------------------------ attendance */
  var sheet = document.getElementById("attendance-form");
  if (sheet) {
    var rows = sheet.querySelectorAll("[data-row]");
    var counter = sheet.querySelector("[data-marked]");
    var count = function () {
      var marked = 0;
      rows.forEach(function (row) { if (row.querySelector("input[type=radio]:checked")) marked++; });
      if (counter) counter.textContent = marked;
    };
    sheet.addEventListener("change", count);

    sheet.addEventListener("click", function (event) {
      var toggle = event.target.closest("[data-ot-toggle]");
      if (toggle) {
        var box = toggle.closest("td").querySelector(".mon-ot-box");
        var opening = box.classList.contains("d-none");
        box.classList.toggle("d-none", !opening);
        toggle.classList.toggle("active", opening);
        toggle.setAttribute("aria-expanded", String(opening));
        var hours = box.querySelector("input");
        if (opening) { hours.focus(); } else { hours.value = ""; }
        return;
      }
      if (event.target.closest("[data-all-present]")) {
        rows.forEach(function (row) {
          if (!row.querySelector("input[type=radio]:checked")) {
            var present = row.querySelector("input[value=present]");
            if (present) present.checked = true;
          }
        });
        count();
      }
    });
  }

  /* ------------------------------------------------ calendar: a day's overtime */
  var box = document.getElementById("overtime-box");
  if (box && window.bootstrap) {
    var modal = bootstrap.Modal.getOrCreateInstance(box);
    document.addEventListener("click", function (event) {
      var day = event.target.closest(".mon-day[data-date]");
      if (!day || day.disabled) return;
      box.querySelector("[name=date]").value = day.getAttribute("data-date");
      box.querySelector("[name=hours]").value = day.getAttribute("data-hours") || "";
      box.querySelector("[data-overtime-day]").textContent =
        day.getAttribute("data-label") + " · " + day.getAttribute("data-status");
      modal.show();
    });
    box.addEventListener("shown.bs.modal", function () { box.querySelector("[name=hours]").focus(); });
  }

  /* ------------------------------------------------------- today's work */
  var work = document.querySelector(".mon-work");
  if (!work) return;

  function note(text, tone) {
    work.querySelectorAll("[data-work-note]").forEach(function (element) {
      element.textContent = text;
      element.className = "small mt-3 " + (tone === "bad" ? "text-danger" : "text-muted");
    });
  }

  function csrf() {
    var found = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return found ? decodeURIComponent(found[1]) : "";
  }

  // The phone's location right now — never a remembered one.
  function locate() {
    return new Promise(function (resolve, reject) {
      if (!("geolocation" in navigator)) {
        reject(new Error("This phone or browser cannot share its location."));
        return;
      }
      navigator.geolocation.getCurrentPosition(resolve, function (problem) {
        var reasons = {
          1: "Location is turned off for this app. Allow it — the lock or ⓘ beside the address, or the app's settings → Location — then try again.",
          2: "The phone could not find where it is. Turn on location (GPS) and try again.",
          3: "Finding the location took too long. Step outside or turn on GPS, and try again.",
        };
        reject(new Error(reasons[problem.code] || "Could not get the location."));
      }, { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
    });
  }

  function send(url, extra) {
    return locate().then(function (position) {
      var body = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
      };
      Object.keys(extra || {}).forEach(function (key) { body[key] = extra[key]; });
      return fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify(body),
      });
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (answer) {
        if (!response.ok || !answer.ok) throw new Error(answer.error || "It could not be saved. Try again.");
        return answer;
      });
    });
  }

  var form = work.querySelector("[data-stop-form]");
  var opener = work.querySelector("[data-work=open-stop]");

  work.addEventListener("click", function (event) {
    var button = event.target.closest("[data-work]");
    if (!button) return;
    var action = button.getAttribute("data-work");

    if (action === "start") {
      button.disabled = true;
      note("Getting your location…");
      send(work.getAttribute("data-start-url")).then(function () {
        window.location.reload();
      }).catch(function (problem) {
        note(problem.message, "bad");
        button.disabled = false;
      });
    } else if (action === "open-stop") {
      opener.classList.add("d-none");
      form.classList.remove("d-none");
      form.querySelector("textarea").focus();
      note("");
    } else if (action === "cancel-stop") {
      form.classList.add("d-none");
      opener.classList.remove("d-none");
      note("");
    }
  });

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var remark = form.querySelector("textarea").value.trim();
      if (!remark) { note("Write a remark about this site.", "bad"); return; }
      var submit = form.querySelector("[data-work=submit-stop]");
      submit.disabled = true;
      note("Getting your location…");
      send(work.getAttribute("data-stop-url"), { remark: remark }).then(function () {
        // Back to the button, ready for the next site, with this one in the list.
        window.location.reload();
      }).catch(function (problem) {
        note(problem.message, "bad");
        submit.disabled = false;
      });
    });
  }
})();
