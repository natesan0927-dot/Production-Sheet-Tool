/* Scan-to-PDF.
 *
 * Staff photograph measurement sheets at site. This collects the photos,
 * sends them to the server to be joined into one PDF, and drops the result
 * into the ordinary file box on the form they are already filling in — so a
 * scan is submitted by the same button as a file they picked themselves.
 *
 * The pages never sit in the page's own form: they are held here until the
 * PDF is made, which keeps a half-finished scan from being posted by accident.
 */
(function () {
  "use strict";

  function token(root) {
    var field = root.closest("form") && root.closest("form").querySelector("[name=csrfmiddlewaretoken]");
    if (field) return field.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function setup(root) {
    var target = document.getElementById(root.dataset.target);
    if (!target) return;

    var body = root.querySelector("[data-scan-body]");
    var picker = root.querySelector("[data-scan-input]");
    var list = root.querySelector("[data-scan-list]");
    var nameBox = root.querySelector("[data-scan-name]");
    var make = root.querySelector("[data-scan-make]");
    var status = root.querySelector("[data-scan-status]");
    var pages = [];

    function say(text, tone) {
      status.textContent = text || "";
      status.className = "small " + (tone || "text-muted");
    }

    function draw() {
      list.innerHTML = "";
      pages.forEach(function (page, index) {
        var item = document.createElement("li");
        item.className = "tw-scan-page";

        var thumb = document.createElement("img");
        thumb.alt = "";
        thumb.src = URL.createObjectURL(page);
        thumb.onload = function () { URL.revokeObjectURL(thumb.src); };

        var label = document.createElement("span");
        label.className = "tw-scan-page-name";
        label.textContent = "Page " + (index + 1);

        var drop = document.createElement("button");
        drop.type = "button";
        drop.className = "btn btn-sm btn-link text-danger p-0";
        drop.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        drop.title = "Remove this page";
        drop.addEventListener("click", function () {
          pages.splice(index, 1);
          draw();
        });

        item.append(thumb, label, drop);
        list.appendChild(item);
      });
      make.disabled = pages.length === 0;
      if (pages.length) say(pages.length + (pages.length === 1 ? " page ready" : " pages ready"));
    }

    // Enter in the name box makes the PDF. Left alone it would submit the whole
    // stage form around this panel, before the scan was attached.
    nameBox.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      event.preventDefault();
      if (!make.disabled) make.click();
    });

    root.querySelector("[data-scan-open]").addEventListener("click", function (event) {
      body.classList.toggle("d-none");
      event.currentTarget.classList.toggle("active", !body.classList.contains("d-none"));
    });

    picker.addEventListener("change", function () {
      Array.prototype.forEach.call(picker.files, function (file) {
        if (file.type.indexOf("image/") === 0) pages.push(file);
      });
      // Cleared so choosing the same photo twice still registers.
      picker.value = "";
      draw();
    });

    make.addEventListener("click", function () {
      if (!pages.length) return;
      var payload = new FormData();
      pages.forEach(function (page) { payload.append("pages", page); });
      payload.append("name", nameBox.value || "");

      make.disabled = true;
      say("Making the PDF…");

      fetch(root.dataset.url, {
        method: "POST",
        headers: { "X-CSRFToken": token(root) },
        body: payload,
        credentials: "same-origin"
      })
        .then(function (response) {
          if (!response.ok) return response.text().then(function (text) { throw new Error(text); });
          var named = "Scan.pdf";
          try { named = decodeURIComponent(response.headers.get("X-Scan-Filename") || named); } catch (e) { /* keep the fallback */ }
          return response.blob().then(function (blob) { return { blob: blob, name: named }; });
        })
        .then(function (result) {
          var file = new File([result.blob], result.name, { type: "application/pdf" });
          var carrier = new DataTransfer();
          // A box that takes several files keeps what was already chosen, and the scan joins them.
          if (target.multiple) {
            Array.prototype.forEach.call(target.files, function (chosen) { carrier.items.add(chosen); });
          }
          carrier.items.add(file);
          target.files = carrier.files;
          // Anything watching the file box (validation, previews) should see this.
          target.dispatchEvent(new Event("change", { bubbles: true }));

          pages = [];
          draw();
          make.disabled = true;
          say(result.name + " attached — now submit the form.", "text-success");
        })
        .catch(function (problem) {
          make.disabled = false;
          say(problem.message || "The pages could not be joined. Try again.", "text-danger");
        });
    });

    draw();
    say("");
  }

  document.querySelectorAll("[data-scan]").forEach(setup);
})();
