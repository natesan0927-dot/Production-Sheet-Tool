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
      var given = box.querySelector("[name=advance]");
      if (given) given.value = day.getAttribute("data-advance") || "";
      box.querySelector("[data-overtime-day]").textContent =
        day.getAttribute("data-label") + " · " + day.getAttribute("data-status");
      modal.show();
    });
    box.addEventListener("shown.bs.modal", function () { box.querySelector("[name=hours]").focus(); });
  }

  /* ------------------------------- REPORT: the deduction, then the PDF */
  var report = document.getElementById("report-box");
  if (report && window.bootstrap) {
    var reportModal = bootstrap.Modal.getOrCreateInstance(report);
    var reportForm = report.querySelector("[data-report-form]");
    var reportLink = document.querySelector("[data-report-link]");
    var current = null;
    var money = function (value) {
      return Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };
    var put = function (name, value) { report.querySelector("[data-report-" + name + "]").textContent = value; };
    var recount = function () {
      var take = Number(reportForm.deduction.value || 0);
      put("pay", money(Number(current.getAttribute("data-salary")) - take));
      put("left", money(Number(current.getAttribute("data-owed")) - take));
    };

    document.addEventListener("click", function (event) {
      var button = event.target.closest("[data-report]");
      if (!button) return;
      current = button;
      put("name", button.getAttribute("data-name"));
      put("month", button.getAttribute("data-month"));
      ["previous", "received", "owed", "salary"].forEach(function (key) { put(key, money(button.getAttribute("data-" + key))); });
      reportForm.action = button.getAttribute("data-save");
      reportForm.deduction.value = button.getAttribute("data-deduction") || "";
      reportForm.deduction.max = Math.min(Number(button.getAttribute("data-owed")), Number(button.getAttribute("data-salary")));
      put("error", "");
      recount();
      reportModal.show();
    });
    report.addEventListener("shown.bs.modal", function () { reportForm.deduction.focus(); });
    reportForm.deduction.addEventListener("input", recount);

    reportForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var send = reportForm.querySelector("button:not([data-bs-dismiss])");
      send.disabled = true;
      fetch(reportForm.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Accept": "application/json", "X-CSRFToken": reportForm.csrfmiddlewaretoken.value },
        body: new FormData(reportForm),
      }).then(function (response) {
        return response.json().then(function (answer) {
          if (!response.ok || !answer.ok) throw new Error(answer.error || "It could not be saved.");
          return answer;
        });
      }).then(function (answer) {
        current.setAttribute("data-deduction", reportForm.deduction.value || "0");
        reportModal.hide();
        // A real link, so a phone hands the PDF to its own viewer (see app.js).
        reportLink.href = answer.pdf;
        reportLink.click();
      }).catch(function (problem) {
        put("error", problem.message);
      }).then(function () { send.disabled = false; });
    });
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
    } else if (action === "complete") {
      // Just the time: the last site stop already says where the day ended.
      if (!window.confirm("Complete today's work?")) return;
      button.disabled = true;
      fetch(work.getAttribute("data-complete-url"), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: "{}",
      }).then(function (response) {
        if (!response.ok) throw new Error("It could not be saved. Try again.");
        window.location.reload();
      }).catch(function (problem) {
        note(problem.message, "bad");
        button.disabled = false;
      });
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
