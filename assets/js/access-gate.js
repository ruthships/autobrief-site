(function () {
	"use strict";

	var STORAGE_KEY = "autobrief_access";
	var COOKIE_MAX_AGE = 365 * 24 * 60 * 60;
	// Optional: set to a Formspree, Google Apps Script, or API URL to collect submissions.
	var SUBMIT_URL = "";

	var pendingTarget = null;
	var modalVisible = false;
	var clickListener = null;
	var keyListener = null;
	var accessGranted = false;

	function setCookie(name, value, maxAge) {
		var cookie = name + "=" + encodeURIComponent(value) + "; path=/; max-age=" + maxAge + "; SameSite=Lax";

		if (window.location.protocol === "https:") {
			cookie += "; Secure";
		}

		document.cookie = cookie;
	}

	function getCookie(name) {
		var pattern = "(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)";
		var match = document.cookie.match(new RegExp(pattern));

		return match ? decodeURIComponent(match[1]) : null;
	}

	function clearCookie(name) {
		document.cookie = name + "=; path=/; max-age=0; SameSite=Lax";
	}

	function parseAccessRecord(raw) {
		if (!raw) {
			return null;
		}

		try {
			var record = JSON.parse(raw);

			if (
				record &&
				typeof record.name === "string" &&
				record.name.trim().length >= 2 &&
				typeof record.email === "string" &&
				isValidEmail(record.email.trim())
			) {
				return {
					name: record.name.trim(),
					email: record.email.trim(),
					grantedAt: record.grantedAt || new Date().toISOString()
				};
			}
		} catch (error) {
			return null;
		}

		return null;
	}

	function readLocalAccess() {
		try {
			return parseAccessRecord(localStorage.getItem(STORAGE_KEY));
		} catch (error) {
			return null;
		}
	}

	function readCookieAccess() {
		return parseAccessRecord(getCookie(STORAGE_KEY));
	}

	function persistAccess(record) {
		var stored = {
			name: record.name,
			email: record.email,
			grantedAt: record.grantedAt || new Date().toISOString()
		};
		var serialized = JSON.stringify(stored);

		try {
			localStorage.setItem(STORAGE_KEY, serialized);
		} catch (error) {
			// Continue even if localStorage is unavailable.
		}

		setCookie(STORAGE_KEY, serialized, COOKIE_MAX_AGE);
		accessGranted = true;
	}

	function syncAccessStorage() {
		var localRecord = readLocalAccess();
		var cookieRecord = readCookieAccess();
		var record = localRecord || cookieRecord;

		if (!record) {
			accessGranted = false;
			return null;
		}

		persistAccess(record);
		return record;
	}

	function isGranted() {
		return accessGranted;
	}

	function isModalElement(element) {
		return element && element.closest && element.closest("#autobrief-access-gate");
	}

	function isInteractive(element) {
		if (!element || !element.closest) {
			return false;
		}

		return !!element.closest(
			"a, button, input, select, textarea, summary, label, [role='button'], .mejs-button, .mejs-overlay-button, .site-menu-toggle a"
		);
	}

	function isValidEmail(value) {
		return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
	}

	function updateSubmitState(form) {
		var nameInput = form.querySelector("#autobrief-access-name");
		var emailInput = form.querySelector("#autobrief-access-email");
		var submitButton = form.querySelector("#autobrief-access-submit");
		var name = nameInput.value.trim();
		var email = emailInput.value.trim();

		submitButton.disabled = name.length < 2 || !isValidEmail(email);
	}

	function saveAccess(name, email) {
		var record = {
			name: name,
			email: email,
			grantedAt: new Date().toISOString(),
			page: window.location.pathname + window.location.search,
			referrer: document.referrer || ""
		};

		persistAccess(record);

		if (SUBMIT_URL) {
			fetch(SUBMIT_URL, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(record),
				keepalive: true
			}).catch(function () {});
		}
	}

	function unlockSite() {
		document.body.classList.remove("autobrief-gated", "autobrief-gate-open");

		if (clickListener) {
			document.removeEventListener("click", clickListener, true);
			clickListener = null;
		}

		if (keyListener) {
			document.removeEventListener("keydown", keyListener, true);
			keyListener = null;
		}
	}

	function hideModal() {
		modalVisible = false;
		document.body.classList.remove("autobrief-gate-open");
	}

	function showModal(target) {
		pendingTarget = target;
		modalVisible = true;
		document.body.classList.add("autobrief-gate-open");

		var nameInput = document.getElementById("autobrief-access-name");
		if (nameInput) {
			window.setTimeout(function () {
				nameInput.focus();
			}, 50);
		}
	}

	function replayPendingAction() {
		if (!pendingTarget) {
			return;
		}

		var target = pendingTarget;
		pendingTarget = null;

		window.setTimeout(function () {
			if (typeof target.click === "function") {
				target.click();
			}
		}, 0);
	}

	function handleBlockedInteraction(event, target) {
		if (isGranted() || isModalElement(target) || !isInteractive(target)) {
			return false;
		}

		event.preventDefault();
		event.stopPropagation();
		event.stopImmediatePropagation();

		if (!modalVisible) {
			showModal(target);
		}

		return true;
	}

	function createModal() {
		if (document.getElementById("autobrief-access-gate")) {
			return;
		}

		var overlay = document.createElement("div");
		overlay.id = "autobrief-access-gate";
		overlay.className = "autobrief-access-gate";
		overlay.setAttribute("role", "dialog");
		overlay.setAttribute("aria-modal", "true");
		overlay.setAttribute("aria-labelledby", "autobrief-access-title");
		overlay.innerHTML =
			'<div class="autobrief-access-gate__backdrop" aria-hidden="true"></div>' +
			'<div class="autobrief-access-gate__panel">' +
			'<h2 id="autobrief-access-title" class="autobrief-access-gate__title">Access AutoBrief</h2>' +
			'<p class="autobrief-access-gate__intro">Enter your name and work email to continue. We use this to understand who is listening.</p>' +
			'<form id="autobrief-access-form" class="autobrief-access-gate__form" novalidate>' +
			'<label class="autobrief-access-gate__label" for="autobrief-access-name">Name</label>' +
			'<input class="autobrief-access-gate__input" id="autobrief-access-name" name="name" type="text" autocomplete="name" required placeholder="Your full name">' +
			'<label class="autobrief-access-gate__label" for="autobrief-access-email">Work email</label>' +
			'<input class="autobrief-access-gate__input" id="autobrief-access-email" name="email" type="email" autocomplete="email" required placeholder="you@company.com">' +
			'<button class="button button-color button-filled autobrief-access-gate__submit" id="autobrief-access-submit" type="submit" disabled>Access</button>' +
			"</form>" +
			"</div>";

		document.body.appendChild(overlay);

		var form = overlay.querySelector("#autobrief-access-form");
		var nameInput = overlay.querySelector("#autobrief-access-name");
		var emailInput = overlay.querySelector("#autobrief-access-email");

		nameInput.addEventListener("input", function () {
			updateSubmitState(form);
		});
		emailInput.addEventListener("input", function () {
			updateSubmitState(form);
		});

		form.addEventListener("submit", function (event) {
			event.preventDefault();

			var name = nameInput.value.trim();
			var email = emailInput.value.trim();

			if (name.length < 2 || !isValidEmail(email)) {
				updateSubmitState(form);
				return;
			}

			saveAccess(name, email);
			hideModal();
			unlockSite();
			replayPendingAction();
		});
	}

	function init() {
		syncAccessStorage();

		if (isGranted()) {
			return;
		}

		createModal();
		document.body.classList.add("autobrief-gated");

		clickListener = function (event) {
			handleBlockedInteraction(event, event.target);
		};

		keyListener = function (event) {
			if (event.key !== "Enter" && event.key !== " ") {
				return;
			}

			handleBlockedInteraction(event, event.target);
		};

		document.addEventListener("click", clickListener, true);
		document.addEventListener("keydown", keyListener, true);
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
