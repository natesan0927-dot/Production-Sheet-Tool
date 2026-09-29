/* Titans Windows CRM — notifications on this device.

   Asks once (a small prompt at the top of the page) whether this phone or
   computer should get a notification whenever something needs the person
   signed in. Once allowed, every account used on the device is registered for
   its own notifications, so switching accounts keeps working. Turning them off
   in My profile stops them for the account in use only.

   Needs a browser with Web Push: Chrome and Edge everywhere, Firefox, and on an
   iPhone the app added to the home screen. Anywhere else nothing here shows. */
(function () {
  "use strict";

  var body = document.body;
  var KEY = body.getAttribute("data-push-key");
  var USER = body.getAttribute("data-user");
  var REGISTERED = body.getAttribute("data-push-endpoint") || "";
  if (!KEY || !USER) return;

  var supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  var OFF = "tw-push-off:" + USER;          // this person turned them off on this device
  var LATER = "tw-push-later:" + USER;      // "Not now", until a week has passed

  function remember(name, value) { try { value === null ? localStorage.removeItem(name) : localStorage.setItem(name, value); } catch (e) { /* private mode */ } }
  function recall(name) { try { return localStorage.getItem(name); } catch (e) { return null; } }

  function csrf() {
    var found = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (found) return decodeURIComponent(found[1]);
    var field = document.querySelector("[name=csrfmiddlewaretoken]");
    return field ? field.value : "";
  }

  function call(url, data) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(data || {}),
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (answer) {
        if (!response.ok || answer.ok === false) throw new Error(answer.error || "The server said no (" + response.status + ").");
        return answer;
      });
    });
  }

  function bytes(text) {
    var padded = (text + "===".slice((text.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(padded), out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  function sameKey(subscription) {
    var mine = subscription.options && subscription.options.applicationServerKey;
    if (!mine) return true;
    var a = new Uint8Array(mine), b = bytes(KEY);
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  // The browser's subscription for this device, made with this site's current key.
  function subscription() {
    return navigator.serviceWorker.ready.then(function (registration) {
      return registration.pushManager.getSubscription().then(function (existing) {
        if (existing && !sameKey(existing)) return existing.unsubscribe().then(function () { return null; });
        return existing;
      }).then(function (existing) {
        return existing || registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(KEY) });
      });
    });
  }

  function register() {
    return subscription().then(function (found) {
      return call("/push/subscribe/", found.toJSON()).then(function () {
        REGISTERED = found.endpoint;
        remember(OFF, null);
        return found;
      });
    });
  }

  function state() {
    if (!supported) return "unsupported";
    if (Notification.permission === "denied") return "blocked";
    if (Notification.permission === "granted" && REGISTERED && recall(OFF) !== "1") return "on";
    return "off";
  }

  /* ------------------------------------------------------------ the page */
  var prompt = document.getElementById("tw-push-prompt");
  var keepPrompt = false;  // it failed from the prompt: leave the reason on screen

  function show(element, visible) {
    if (!element) return;
    element.classList.toggle("d-none", !visible);
  }

  function refresh(message, tone) {
    var now = state();
    document.querySelectorAll("[data-push-show]").forEach(function (element) {
      show(element, element.getAttribute("data-push-show").split(" ").indexOf(now) !== -1);
    });
    if (message !== undefined) {
      document.querySelectorAll("[data-push-note]").forEach(function (note) {
        note.textContent = message;
        note.className = "d-block small mt-1 " + (tone === "bad" ? "text-danger" : "text-success");
      });
    }
    var later = Number(recall(LATER) || 0);
    var asking = supported && now === "off" && Notification.permission === "default" && recall(OFF) !== "1" && Date.now() > later;
    show(prompt, keepPrompt || asking);
  }

  function turnOn() {
    return Notification.requestPermission().then(function (answer) {
      if (answer !== "granted") {
        throw new Error(answer === "denied"
          ? "Notifications are blocked for this app. Allow them in the phone's settings, then try again."
          : "Notifications were not allowed.");
      }
      return register();
    });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-push]");
    if (!button) return;
    event.preventDefault();
    var action = button.getAttribute("data-push");
    if (action === "later") {
      remember(LATER, String(Date.now() + 7 * 24 * 3600 * 1000));
      keepPrompt = false;
      show(prompt, false);
      return;
    }
    button.disabled = true;
    var done = function () { button.disabled = false; };
    if (action === "on") {
      turnOn().then(function () { keepPrompt = false; refresh("Notifications are on for this device.", "good"); })
        .catch(function (problem) { keepPrompt = Boolean(prompt && prompt.contains(button)); refresh(problem.message, "bad"); })
        .then(done);
    } else if (action === "off") {
      call("/push/unsubscribe/", { endpoint: REGISTERED }).then(function () {
        REGISTERED = "";
        remember(OFF, "1");
        refresh("Notifications are off for you on this device.", "good");
      }).catch(function (problem) { refresh(problem.message, "bad"); }).then(done);
    } else if (action === "test") {
      call("/push/test/").then(function () { refresh("Sent. It should appear in a few seconds.", "good"); })
        .catch(function (problem) { refresh(problem.message, "bad"); }).then(done);
    }
  });

  if (!supported) { refresh(); return; }

  // Allowed on this device before (perhaps under another account): make sure the
  // person signed in now is registered too, without asking again.
  if (Notification.permission === "granted" && recall(OFF) !== "1") {
    subscription().then(function (found) {
      if (found.endpoint !== REGISTERED) return register();
    }).catch(function () { /* tried again on the next page */ }).then(function () { refresh(); });
  }
  refresh();
})();
