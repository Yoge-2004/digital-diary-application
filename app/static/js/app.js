/* ============================================================
   Digital Diary — app.js v2
   Full validation + animations + forgot-password + count-up
   ============================================================ */

(() => {
  "use strict";

  // ══════════════════════════════════════════════════════════
  //  Constants / Helpers
  // ══════════════════════════════════════════════════════════
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  const THEME_KEY = "dd-theme";
  const DRAFT_PREFIX = "dd-draft-";

  // Toggle a button's loading state, guaranteeing a .btn-spinner span
  // exists (some templates already include one statically; for any
  // button that doesn't, insert one) so the spinner always participates
  // in normal flex flow next to the label instead of relying on a
  // ::after pseudo-element, which doesn't position reliably here.
  function setBtnLoading(btn, isLoading) {
    if (!btn) return;
    if (isLoading) {
      if (!btn.querySelector(".btn-spinner")) {
        const spinner = document.createElement("span");
        spinner.className = "btn-spinner";
        spinner.setAttribute("aria-hidden", "true");
        btn.appendChild(spinner);
      }
      btn.classList.add("loading");
    } else {
      btn.classList.remove("loading");
    }
  }

  // ══════════════════════════════════════════════════════════
  //  Theme (dark / light)
  // ══════════════════════════════════════════════════════════
  // Same hsl(...) values as --bg-body in :root / [data-theme="dark"]
  // in app.css, converted to hex since <meta name="theme-color">
  // doesn't take a live CSS variable -- this is the one place that
  // value has to be duplicated. Drives the browser's own chrome color
  // (mobile status bar, task-switcher card, desktop PWA title bar),
  // which used to be a single hardcoded brown (#7c4a1e, a leftover
  // from before the "Confession Ink" redesign) that never changed
  // with the theme toggle at all.
  const THEME_COLOR = { light: "#f9f9fb", dark: "#0f0d17" };

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
    $$(".theme-toggle").forEach((btn) => {
      const icon = btn.querySelector("i");
      const label = btn.querySelector(".theme-label");
      if (icon) icon.className = theme === "dark" ? "bi bi-sun-fill" : "bi bi-moon-fill";
      if (label) label.textContent = theme === "dark" ? "Light" : "Dark";
    });
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", THEME_COLOR[theme] || THEME_COLOR.light);
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    applyTheme(saved || preferred);
  }

  // Expose globally so settings page inline button can call it
  window.applyThemeBtn = (t) => {
    if (!t) {
      t = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    applyTheme(t);
  };

  document.addEventListener("click", (e) => {
    if (e.target.closest(".theme-toggle")) {
      const current = document.documentElement.getAttribute("data-theme") || "light";
      applyTheme(current === "dark" ? "light" : "dark");
    }
  });

  // A page reached via the browser's Back/Forward buttons is very often
  // restored from the back-forward cache (bfcache) instead of actually
  // reloading -- the browser freezes the page's exact DOM/JS state when
  // you navigate away and thaws that same snapshot back rather than
  // re-running any scripts. initTheme() above only ever runs once, at
  // the moment this script first executes, so a bfcache-restored page
  // keeps showing whatever theme was true *when it was cached* even if
  // the theme was changed on a different page (or a different tab) in
  // the meantime and localStorage has since moved on. `pageshow` fires
  // on every page view including bfcache restores, and its `persisted`
  // flag is exactly how to tell the two apart -- re-run initTheme()
  // only for the restore case, since a normal fresh load already got it
  // right the first time.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) initTheme();
  });

  // Same underlying problem, different trigger: two tabs open on this
  // app, theme changed in one, the other tab's DOM never hears about it
  // either (it's not bfcache-frozen, it's just sitting there with no
  // reason to re-check localStorage). The `storage` event fires in
  // *other* tabs/windows whenever localStorage changes (never in the
  // tab that made the change), so this is the missing other half.
  window.addEventListener("storage", (event) => {
    if (event.key === THEME_KEY && event.newValue) applyTheme(event.newValue);
  });

  // ══════════════════════════════════════════════════════════
  //  Button ripple effect
  // ══════════════════════════════════════════════════════════
  function initRipple() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".btn");
      if (!btn || btn.classList.contains("no-ripple")) return;
      const rect = btn.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 2.5;
      const x = e.clientX - rect.left - size / 2;
      const y = e.clientY - rect.top - size / 2;
      const ripple = document.createElement("span");
      ripple.className = "ripple";
      ripple.style.cssText = `width:${size}px;height:${size}px;left:${x}px;top:${y}px`;
      btn.appendChild(ripple);
      ripple.addEventListener("animationend", () => ripple.remove());
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Sidebar mobile toggle
  // ══════════════════════════════════════════════════════════
  // ══════════════════════════════════════════════════════════
  //  Island quick-nav (disclosure pattern)
  // ══════════════════════════════════════════════════════════
  function initIsland() {
    const island = $("#island");
    const toggle = $("#islandToggle");
    if (!island || !toggle) return;

    function setOpen(open, returnFocus) {
      island.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open && returnFocus) toggle.focus();
    }

    toggle.addEventListener("click", () => setOpen(!island.classList.contains("is-open")));

    // Escape closes and puts focus back on the pill if it was inside the menu.
    island.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && island.classList.contains("is-open")) {
        e.stopPropagation();
        setOpen(false, island.contains(document.activeElement));
      }
    });
    // Tabbing out of either end closes it. Tabbing off the last item can leave
    // the page entirely (relatedTarget is null), so null counts as "left" --
    // except while the pointer is pressed inside the island, where it only
    // means the click landed on a non-focusable gap.
    let pressing = false;
    island.addEventListener("pointerdown", () => { pressing = true; });
    document.addEventListener("pointerup", () => { setTimeout(() => { pressing = false; }, 0); });
    island.addEventListener("focusout", (e) => {
      if (pressing || !island.classList.contains("is-open")) return;
      if (!e.relatedTarget || !island.contains(e.relatedTarget)) setOpen(false, false);
    });
    document.addEventListener("pointerdown", (e) => {
      if (island.classList.contains("is-open") && !island.contains(e.target)) setOpen(false, false);
    });
    // A page restored from the back/forward cache must not come back open.
    window.addEventListener("pageshow", (e) => { if (e.persisted) setOpen(false, false); });

    // ---- Adaptive behaviour ------------------------------------------------
    const isOpen = () => island.classList.contains("is-open");

    // 1) Compact while scrolling down, back on scroll up / near the ends / hover.
    function setCompact(on) { island.classList.toggle("is-compact", on); }
    let lastY = window.scrollY;
    let ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const y = window.scrollY;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        // 2) Reading progress hairline.
        island.style.setProperty("--island-progress", max > 0 ? Math.min(1, Math.max(0, y / max)) : 0);
        island.dataset.scrollable = max > 240 ? "true" : "false";
        if (isOpen() || island.contains(document.activeElement)) { lastY = y; return; }
        const dy = y - lastY;
        if (Math.abs(dy) < 8 && y > 80 && max - y > 120) return; // ignore jitter
        if (dy > 0 && y > 160 && max - y > 120) setCompact(true);
        else if (dy < 0 || y < 80 || max - y <= 120) setCompact(false);
        lastY = y;
      });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    // Content can change height after load (fonts, entries arriving, accordions),
    // which changes whether the page scrolls at all and how far along you are.
    if ("ResizeObserver" in window) new ResizeObserver(onScroll).observe(document.body);
    island.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") setCompact(false); });
    island.addEventListener("focusin", () => setCompact(false));
    onScroll();

    // 3) On phones, get out of the way while a text field has focus (the
    //    on-screen keyboard would otherwise sit on top of, or push, the pill).
    const narrow = window.matchMedia("(max-width: 767px)");
    const EDITABLE = 'textarea, [contenteditable]:not([contenteditable="false"]), input:not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([type="range"]):not([type="file"]):not([type="color"])';
    function syncTyping() {
      const el = document.activeElement;
      const typing = narrow.matches && el && !island.contains(el) && el.matches && el.matches(EDITABLE);
      island.classList.toggle("is-typing", !!typing);
      if (typing) setOpen(false, false);
    }
    document.addEventListener("focusin", syncTyping);
    document.addEventListener("focusout", () => setTimeout(syncTyping, 0));
    narrow.addEventListener("change", syncTyping);

    // 4) Live context in the pill: a word count while writing. The visible text
    //    is part of the accessible name (WCAG 2.5.3), so mirror it into aria-label.
    const meta = $("#islandMeta");
    const body = document.getElementById("diaryContent");
    if (meta && body) {
      const base = toggle.dataset.baseLabel || toggle.getAttribute("aria-label") || "";
      const update = () => {
        const n = (body.value.trim().match(/\S+/g) || []).length;
        const text = n ? n + (n === 1 ? " word" : " words") : "";
        meta.textContent = text;
        toggle.setAttribute("aria-label", text ? base + ", " + text : base);
      };
      body.addEventListener("input", update);
      update();
    }
  }

  function initSidebar() {
    const toggle = $("#sidebarToggle");
    const sidebar = $("#appSidebar");
    const overlay = $("#sidebarOverlay");
    const closeBtn = $("#sidebarCloseBtn");
    if (!toggle || !sidebar) return;

    const main = $(".app-main");
    const mobile = window.matchMedia("(max-width: 1023px)");

    function openSidebar() {
      sidebar.classList.add("open");
      overlay?.classList.add("open");
      toggle.setAttribute("aria-expanded", "true");
      // The drawer is modal: the page behind it must not be reachable by Tab,
      // and focus has to move into it or a keyboard user stays on the toggle.
      if (main) main.inert = true;
      closeBtn?.focus();
    }

    function closeSidebar(returnFocus) {
      const hadFocus = sidebar.contains(document.activeElement);
      sidebar.classList.remove("open");
      overlay?.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
      if (main) main.inert = false;
      // Put focus back where the user opened it (otherwise it falls to <body>
      // and the next Tab starts from the top of the page).
      if (returnFocus || hadFocus) toggle.focus();
    }

    toggle.addEventListener("click", () => {
      if (sidebar.classList.contains("open")) closeSidebar(true); else openSidebar();
    });
    closeBtn?.addEventListener("click", () => closeSidebar(true));
    overlay?.addEventListener("click", () => closeSidebar(false));

    // Escape key closes mobile sidebar
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && sidebar.classList.contains("open")) {
        closeSidebar(true);
      }
    });

    // Rotating/resizing to desktop with the drawer open would leave the page inert.
    mobile.addEventListener("change", (e) => {
      if (!e.matches && sidebar.classList.contains("open")) closeSidebar(false);
    });

    // Swipe left to close on mobile
    let touchStartX = 0;
    sidebar.addEventListener("touchstart", (e) => { touchStartX = e.changedTouches[0].screenX; }, { passive: true });
    sidebar.addEventListener("touchend", (e) => {
      if (touchStartX - e.changedTouches[0].screenX > 60) closeSidebar(true);
    }, { passive: true });
  }

  // ══════════════════════════════════════════════════════════
  //  Flash messages
  // ══════════════════════════════════════════════════════════
  function initFlash() {
    $$(".flash").forEach((el) => {
      setTimeout(() => dismissFlash(el), 4500);
    });
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".flash-close");
      if (btn) dismissFlash(btn.closest(".flash"));
    });
  }

  function dismissFlash(el) {
    if (!el || el._dismissing) return;
    el._dismissing = true;
    el.style.transition = "opacity 0.3s ease, transform 0.3s ease";
    el.style.opacity = "0";
    el.style.transform = "translateX(30px) scale(0.95)";
    setTimeout(() => el.remove(), 320);
  }

  // Show programmatic flash
  function showFlash(message, type = "success") {
    const container = document.getElementById("flashContainer");
    if (!container) return;
    const icon = type === "success" ? "bi-check-circle-fill" : "bi-exclamation-triangle-fill";
    const el = document.createElement("div");
    el.className = `flash flash-${type}`;
    el.innerHTML = `
      <i class="bi ${icon}"></i>
      <span>${message}</span>
      <button class="flash-close" aria-label="Close">✕</button>`;
    container.appendChild(el);
    setTimeout(() => dismissFlash(el), 4500);
  }

  // ══════════════════════════════════════════════════════════
  //  Password toggle show/hide
  // ══════════════════════════════════════════════════════════
  function initPasswordToggle() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".toggle-pw");
      if (!btn) return;
      const wrap = btn.closest(".password-wrap");
      const input = wrap?.querySelector("input");
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      const icon = btn.querySelector("i");
      if (icon) icon.className = show ? "bi bi-eye-slash" : "bi bi-eye";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Password strength meter
  // ══════════════════════════════════════════════════════════
  function scorePassword(pw) {
    let score = 0;
    if (pw.length >= 8)   score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[a-z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score = Math.min(score + 1, 4);
    return Math.min(score, 4);
  }

  function getStrengthLabel(score) {
    return ["", "Weak", "Fair", "Good", "Strong"][score] || "";
  }

  function getStrengthColor(score) {
    return ["", "#e55", "#f90", "#8bc34a", "#4caf50"][score] || "";
  }

  // Wires one password-strength meter instance to its input/fill/label.
  // Pulled out as its own function (rather than the hardcoded
  // "reg-password" ids this used to be stuck with) because the exact
  // same meter markup -- .pw-strength > .pw-strength-bar > .pw-strength-fill
  // plus a .pw-strength-label -- shows up on three different pages
  // (register, settings > change password, reset password), each with
  // its own input/fill/label ids. Register was the only one actually
  // getting wired up before; settings and reset-password rendered a
  // meter that just... never moved, since nothing was listening on
  // their inputs.
  function wireStrengthMeter(inputId, fillId, labelId) {
    const pwInput = document.getElementById(inputId);
    const fill = document.getElementById(fillId);
    const label = labelId ? document.getElementById(labelId) : null;
    if (!pwInput || !fill) return;

    // Requirement items
    const reqLen   = document.getElementById("req-len");
    const reqUpper = document.getElementById("req-upper");
    const reqLower = document.getElementById("req-lower");
    const reqNum   = document.getElementById("req-num");

    pwInput.addEventListener("input", () => {
      const pw = pwInput.value;
      const score = scorePassword(pw);
      fill.setAttribute("data-strength", score > 0 ? score : "");
      fill.style.width = score > 0 ? `${score * 25}%` : "0%";
      fill.style.background = getStrengthColor(score);
      if (label) {
        label.textContent = pw.length > 0 ? getStrengthLabel(score) : "";
        // Colour comes from CSS ([data-strength]) so it can use text-safe
        // tokens; the bar fill keeps getStrengthColor().
        label.dataset.strength = score > 0 ? score : "";
      }

      // Requirements
      const mark = (el, met) => {
        if (!el) return;
        el.classList.toggle("met", met);
        const icon = el.querySelector("i");
        if (icon) icon.className = met ? "bi bi-check-circle-fill" : "bi bi-circle";
      };

      mark(reqLen,   pw.length >= 8);
      mark(reqUpper, /[A-Z]/.test(pw));
      mark(reqLower, /[a-z]/.test(pw));
      mark(reqNum,   /[0-9]/.test(pw));

      // Also trigger confirm match if filled (register page only --
      // harmless no-op elsewhere since #reg-confirm won't exist there)
      const confirm = document.getElementById("reg-confirm");
      if (confirm && confirm.value) validateConfirmPassword();
    });
  }

  function initPasswordStrength() {
    wireStrengthMeter("reg-password", "pwStrengthFill", "pwStrengthLabel"); // Register
    wireStrengthMeter("new-pw", "pwStrengthFill", "pwStrengthLabel");       // Settings > change password
    wireStrengthMeter("rp-new", "rp-strength-fill", "rp-strength-label");  // Reset password
  }

  // ══════════════════════════════════════════════════════════
  //  Validation helpers
  // ══════════════════════════════════════════════════════════
  function setValid(input, msg = "") {
    input.classList.remove("is-invalid");
    input.classList.add("is-valid");
    const fb = input.closest(".form-group")?.querySelector(".form-feedback");
    if (fb) {
      fb.className = "form-feedback valid";
      fb.innerHTML = msg ? `<i class="bi bi-check-circle-fill"></i> ${msg}` : "";
    }
  }

  function setInvalid(input, msg) {
    input.classList.remove("is-valid");
    input.classList.add("is-invalid");
    const fb = input.closest(".form-group")?.querySelector(".form-feedback");
    if (fb) {
      fb.className = "form-feedback invalid";
      fb.innerHTML = `<i class="bi bi-exclamation-circle-fill"></i> ${msg}`;
    }
  }

  function clearState(input) {
    input.classList.remove("is-valid", "is-invalid");
    const fb = input.closest(".form-group")?.querySelector(".form-feedback");
    if (fb) { fb.className = "form-feedback"; fb.innerHTML = ""; }
  }

  function shakeForm(form) {
    form.classList.remove("shake");
    void form.offsetWidth; // reflow to restart animation
    form.classList.add("shake");
    form.addEventListener("animationend", () => form.classList.remove("shake"), { once: true });
  }

  // ── Username validation ──
  function validateUsername(input) {
    const val = input.value.trim();
    if (!val) { setInvalid(input, "Username is required"); return false; }
    if (val.length < 3) { setInvalid(input, "Must be at least 3 characters"); return false; }
    if (val.length > 50) { setInvalid(input, "Must be 50 characters or less"); return false; }
    if (!/^[a-zA-Z0-9_]+$/.test(val)) { setInvalid(input, "Only letters, numbers and underscores allowed"); return false; }
    setValid(input, "Looks good!");
    return true;
  }

  // ── Email validation ──
  function validateEmail(input) {
    const val = input.value.trim();
    if (!val) { setInvalid(input, "Email is required"); return false; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) { setInvalid(input, "Enter a valid email address"); return false; }
    setValid(input, "Looks good!");
    return true;
  }

  // ── Password validation ──
  function validatePassword(input) {
    const val = input.value;
    if (!val) { setInvalid(input, "Password is required"); return false; }
    if (val.length < 8) { setInvalid(input, "Must be at least 8 characters"); return false; }
    const score = scorePassword(val);
    if (score < 2) { setInvalid(input, "Password is too weak — add uppercase, numbers, or symbols"); return false; }
    setValid(input);
    return true;
  }

  // ── Confirm password ──
  function validateConfirmPassword() {
    const pw = document.getElementById("reg-password");
    const confirm = document.getElementById("reg-confirm");
    if (!pw || !confirm) return true;
    if (!confirm.value) { setInvalid(confirm, "Please confirm your password"); return false; }
    if (pw.value !== confirm.value) { setInvalid(confirm, "Passwords do not match"); return false; }
    setValid(confirm, "Passwords match!");
    return true;
  }

  // ── General required field ──
  function validateRequired(input, label = "This field") {
    if (!input.value.trim()) {
      setInvalid(input, `${label} is required`);
      return false;
    }
    clearState(input);
    return true;
  }

  // ══════════════════════════════════════════════════════════
  //  Register form
  // ══════════════════════════════════════════════════════════
  function initRegisterForm() {
    const form = document.getElementById("registerForm");
    if (!form) return;

    const username = document.getElementById("reg-username");
    const email    = document.getElementById("reg-email");
    const password = document.getElementById("reg-password");
    const confirm  = document.getElementById("reg-confirm");

    // Live validation
    username?.addEventListener("blur", () => validateUsername(username));
    username?.addEventListener("input", () => { if (username.classList.contains("is-invalid")) validateUsername(username); });

    email?.addEventListener("blur", () => validateEmail(email));
    email?.addEventListener("input", () => { if (email.classList.contains("is-invalid")) validateEmail(email); });

    password?.addEventListener("blur", () => validatePassword(password));

    confirm?.addEventListener("input", validateConfirmPassword);
    confirm?.addEventListener("blur", validateConfirmPassword);

    form.addEventListener("submit", (e) => {
      const uOk = validateUsername(username);
      const eOk = validateEmail(email);
      const pOk = validatePassword(password);
      const cOk = validateConfirmPassword();

      if (!uOk || !eOk || !pOk || !cOk) {
        e.preventDefault();
        shakeForm(form);
        // Focus first invalid field
        const firstInvalid = form.querySelector(".is-invalid");
        firstInvalid?.focus();
        return;
      }

      // Show loading state
      const btn = form.querySelector('[type="submit"]');
      if (btn) {
        setBtnLoading(btn, true);
        btn.disabled = true;
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Login form
  // ══════════════════════════════════════════════════════════
  function initLoginForm() {
    const form = document.getElementById("loginForm");
    if (!form) return;

    const username = document.getElementById("login-username");
    const password = document.getElementById("login-password");

    username?.addEventListener("blur", () => validateRequired(username, "Username or email"));
    password?.addEventListener("blur", () => validateRequired(password, "Password"));

    form.addEventListener("submit", (e) => {
      const uOk = validateRequired(username, "Username or email");
      const pOk = validateRequired(password, "Password");
      if (!uOk || !pOk) {
        e.preventDefault();
        shakeForm(form);
        form.querySelector(".is-invalid")?.focus();
        return;
      }
      const btn = form.querySelector('[type="submit"]');
      if (btn) { setBtnLoading(btn, true); btn.disabled = true; }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Forgot-password request (always shows the same generic success)
  // ══════════════════════════════════════════════════════════
  function initForgotPasswordForm() {
    const form = document.getElementById("forgotForm");
    if (!form) return;

    const steps = $$(".forgot-step", form);
    function showStep(idx) {
      steps.forEach((s, i) => { s.style.display = i === idx ? "block" : "none"; });
    }
    showStep(0);

    const verifyBtn = document.getElementById("verifyBtn");
    verifyBtn?.addEventListener("click", async () => {
      const uInput = document.getElementById("fp-username");
      const eInput = document.getElementById("fp-email");
      const uOk = validateRequired(uInput, "Username");
      const eOk = validateEmail(eInput);
      if (!uOk || !eOk) { shakeForm(form); return; }

      setBtnLoading(verifyBtn, true);
      verifyBtn.disabled = true;

      try {
        await fetch("/forgot-password/verify", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "",
          },
          body: JSON.stringify({
            username: uInput.value.trim(),
            email: eInput.value.trim(),
          }),
        });
        // Carry the identifier forward so the person doesn't have to type
        // it again on the next page -- not sensitive enough to avoid
        // sessionStorage, and it saves a step.
        try { sessionStorage.setItem("dd-reset-identifier", uInput.value.trim()); } catch {}
        // Always show the same generic "check your email" step, whether
        // or not an account actually matched — this is deliberate, so the
        // form can't be used to check which usernames/emails exist.
        showStep(1);
      } catch {
        showFlash("Something went wrong. Please try again.", "error");
      } finally {
        setBtnLoading(verifyBtn, false);
        verifyBtn.disabled = false;
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Reset password (code-gated: identifier + emailed OTP code)
  // ══════════════════════════════════════════════════════════
  function initResetPasswordForm() {
    const form = document.getElementById("resetPwForm");
    if (!form) return;

    const resetBtn = document.getElementById("resetPwBtn");
    resetBtn?.addEventListener("click", async () => {
      const idInput = document.getElementById("rp-identifier");
      const codeInput = document.getElementById("rp-code");
      const npInput = document.getElementById("rp-new");
      const cnfInput = document.getElementById("rp-confirm");

      const idOk = validateRequired(idInput, "Username or email");
      const codeOk = validateRequired(codeInput, "Verification code");
      const pOk = validatePassword(npInput);
      if (!idOk || !codeOk || !pOk) { shakeForm(form); return; }
      if (npInput.value !== cnfInput.value) {
        setInvalid(cnfInput, "Passwords do not match");
        shakeForm(form);
        return;
      }

      setBtnLoading(resetBtn, true);
      resetBtn.disabled = true;

      try {
        const resp = await fetch("/reset-password", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "",
          },
          body: JSON.stringify({
            identifier: idInput.value.trim(),
            code: codeInput.value.trim(),
            new_password: npInput.value,
            confirm_new_password: cnfInput.value,
          }),
        });
        const data = await resp.json();
        if (resp.ok && data.ok) {
          try { sessionStorage.removeItem("dd-reset-identifier"); } catch {}
          form.style.display = "none";
          const success = document.getElementById("resetPwSuccess");
          if (success) success.style.display = "block";
        } else {
          showFlash(data.detail || "That code is invalid or has expired. Please request a new one.", "error");
        }
      } catch {
        showFlash("Something went wrong. Please try again.", "error");
      } finally {
        setBtnLoading(resetBtn, false);
        resetBtn.disabled = false;
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Mood selector
  // ══════════════════════════════════════════════════════════
  function initMoodSelector() {
    const selector = document.getElementById("moodSelector");
    const hiddenInput = document.getElementById("moodInput");
    if (!selector || !hiddenInput) return;

    selector.querySelectorAll(".mood-option").forEach((opt) => {
      opt.addEventListener("click", () => {
        selector.querySelectorAll(".mood-option").forEach((o) => o.classList.remove("selected"));
        opt.classList.add("selected");
        hiddenInput.value = opt.dataset.mood;
        // Clear any validation error on mood
        clearState(hiddenInput);
      });
    });

    // Pre-select current value
    const current = hiddenInput.value;
    if (current) {
      selector.querySelectorAll(".mood-option").forEach((o) => {
        if (o.dataset.mood === current) o.classList.add("selected");
      });
    }
  }

  // ══════════════════════════════════════════════════════════
  //  Tag pill preview (with pop animation)
  // ══════════════════════════════════════════════════════════
  function initTagInput() {
    const input   = document.getElementById("tagsInput");
    const preview = document.getElementById("tagPillsPreview");
    if (!input || !preview) return;

    let lastTags = [];

    function renderPills(raw) {
      const tags = raw.split(",").map((t) => t.trim()).filter(Boolean);
      // Find new tags
      const newTags = tags.filter((t) => !lastTags.includes(t));
      preview.innerHTML = tags.map((t) => {
        const isNew = newTags.includes(t);
        return `<span class="tag-badge${isNew ? " tag-new" : ""}"><i class="bi bi-hash"></i>${t}</span>`;
      }).join("");
      lastTags = [...tags];
    }

    input.addEventListener("input", () => renderPills(input.value));
    renderPills(input.value);
  }

  // ══════════════════════════════════════════════════════════
  //  Word / character count
  // ══════════════════════════════════════════════════════════
  function initWordCount() {
    const textarea = document.getElementById("diaryContent");
    const counter = document.getElementById("wordCount");
    const charCounter = document.getElementById("charCount");
    if (!textarea || !counter) return;

    function update() {
      const text  = textarea.value.trim();
      const words = text ? (text.match(/\S+/g)?.length || 0) : 0;
      const chars = textarea.value.length;
      counter.textContent = `${words} word${words !== 1 ? "s" : ""}`;
      if (charCounter) {
        charCounter.textContent = `${chars} char${chars !== 1 ? "s" : ""}`;
      }

      // Validate minimum
      if (chars > 0 && chars < 10) {
        setInvalid(textarea, "Please write a bit more (at least 10 characters)");
      } else if (chars >= 10) {
        clearState(textarea);
      }
    }

    textarea.addEventListener("input", update);
    update();
  }

  // ══════════════════════════════════════════════════════════
  //  Title character counter
  // ══════════════════════════════════════════════════════════
  function initTitleCounter() {
    const titleInput = document.getElementById("diaryTitle");
    const counter    = document.getElementById("titleCount");
    if (!titleInput || !counter) return;

    function update() {
      const len = titleInput.value.length;
      counter.textContent = `${len}/255`;
      counter.style.color = len > 240 ? "var(--clr-danger)" : len > 200 ? "var(--clr-accent-dark)" : "var(--txt-muted)";
    }

    titleInput.addEventListener("input", update);
    update();
  }

  // ══════════════════════════════════════════════════════════
  //  Auto-save draft
  // ══════════════════════════════════════════════════════════
  function initAutosave() {
    const form      = document.getElementById("diaryForm");
    const indicator = document.getElementById("autosaveIndicator");
    if (!form) return;

    const key  = `${DRAFT_PREFIX}${window.location.pathname}`;
    const isCreate = window.location.pathname.endsWith("/new");

    // Restore draft only on create page
    if (isCreate) {
      const saved = localStorage.getItem(key);
      if (saved) {
        try {
          const data = JSON.parse(saved);
          const titleEl   = form.querySelector('[name="title"]');
          const contentEl = form.querySelector('[name="content"]');
          if (titleEl   && !titleEl.value   && data.title)   titleEl.value = data.title;
          if (contentEl && !contentEl.value && data.content) contentEl.value = data.content;
          if (indicator) {
            indicator.innerHTML = '<i class="bi bi-clock-history"></i> Draft restored';
            indicator.classList.add("saved");
            setTimeout(() => {
              indicator.innerHTML = '<i class="bi bi-cloud"></i> Auto-save on';
              indicator.classList.remove("saved");
            }, 2500);
          }
          // Trigger word count update
          document.getElementById("diaryContent")?.dispatchEvent(new Event("input"));
        } catch (_) {}
      }
    }

    let saveTimer;
    function saveDraft() {
      const data = {
        title:   form.querySelector('[name="title"]')?.value || "",
        content: form.querySelector('[name="content"]')?.value || "",
        savedAt: new Date().toISOString(),
      };
      localStorage.setItem(key, JSON.stringify(data));
      if (indicator) {
        indicator.innerHTML = '<i class="bi bi-cloud-check-fill"></i> Saved';
        indicator.classList.add("saved");
        setTimeout(() => {
          indicator.innerHTML = '<i class="bi bi-cloud"></i> Auto-save on';
          indicator.classList.remove("saved");
        }, 2000);
      }
    }

    form.addEventListener("input", () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(saveDraft, 1200);
    });

    form.addEventListener("submit", () => {
      localStorage.removeItem(key);
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Diary form validation
  // ══════════════════════════════════════════════════════════
  function initDiaryFormValidation() {
    const form = document.getElementById("diaryForm");
    if (!form) return;

    form.addEventListener("submit", (e) => {
      let ok = true;
      const title   = form.querySelector('[name="title"]');
      const content = form.querySelector('[name="content"]');
      const mood    = form.querySelector('[name="mood"]');

      if (title && !title.value.trim()) {
        setInvalid(title, "Please give your entry a title");
        ok = false;
      }
      if (content && content.value.trim().length < 10) {
        setInvalid(content, "Please write at least 10 characters");
        ok = false;
      }
      if (mood && !mood.value) {
        showFlash("Please select a mood before saving", "error");
        ok = false;
      }

      if (!ok) {
        e.preventDefault();
        shakeForm(form);
        form.querySelector(".is-invalid")?.focus();
      } else {
        const btn = form.querySelector('[type="submit"]');
        if (btn) { setBtnLoading(btn, true); btn.disabled = true; }
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Settings form validation
  // ══════════════════════════════════════════════════════════
  function initSettingsValidation() {
    // Profile form
    const profileForm = document.getElementById("profileForm");
    if (profileForm) {
      const uInput = profileForm.querySelector('[name="username"]');
      const eInput = profileForm.querySelector('[name="email"]');
      uInput?.addEventListener("blur", () => validateUsername(uInput));
      eInput?.addEventListener("blur", () => validateEmail(eInput));

      profileForm.addEventListener("submit", (e) => {
        const uOk = validateUsername(uInput);
        const eOk = validateEmail(eInput);
        if (!uOk || !eOk) { e.preventDefault(); shakeForm(profileForm); }
        else {
          const btn = profileForm.querySelector('[type="submit"]');
          if (btn) { setBtnLoading(btn, true); btn.disabled = true; }
        }
      });
    }

    // Password form
    const pwForm = document.getElementById("passwordForm");
    if (pwForm) {
      const curPw = pwForm.querySelector('[name="current_password"]');
      const newPw = document.getElementById("new-pw");
      const cnfPw = document.getElementById("confirm-new-pw");

      newPw?.addEventListener("input", () => {
        validatePassword(newPw);
        if (cnfPw?.value) validateConfirmPw();
      });
      cnfPw?.addEventListener("input", validateConfirmPw);

      function validateConfirmPw() {
        if (!newPw || !cnfPw) return true;
        if (newPw.value !== cnfPw.value) { setInvalid(cnfPw, "Passwords do not match"); return false; }
        setValid(cnfPw, "Matches!");
        return true;
      }

      pwForm.addEventListener("submit", (e) => {
        const c1 = validateRequired(curPw, "Current password");
        const c2 = validatePassword(newPw);
        const c3 = validateConfirmPw();
        if (!c1 || !c2 || !c3) { e.preventDefault(); shakeForm(pwForm); }
        else {
          const btn = pwForm.querySelector('[type="submit"]');
          if (btn) { setBtnLoading(btn, true); btn.disabled = true; }
        }
      });
    }
  }

  // ══════════════════════════════════════════════════════════
  //  Settings tabs
  // ══════════════════════════════════════════════════════════
  function initSettingsTabs() {
    const tabs   = $$(".settings-tab");
    const panels = $$(".settings-panel");
    if (!tabs.length) return;

    function activateTab(tab) {
      tabs.forEach((t) => t.classList.remove("active"));
      panels.forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      const target = document.getElementById(tab.dataset.panel);
      if (target) target.classList.add("active");
    }

    tabs.forEach((tab) => tab.addEventListener("click", () => activateTab(tab)));

    const hash = window.location.hash.replace("#", "");
    if (hash) {
      const matching = document.querySelector(`[data-panel="${hash}"]`);
      if (matching) activateTab(matching);
      else if (tabs[0]) activateTab(tabs[0]);
    } else if (tabs[0]) activateTab(tabs[0]);
  }

  // ══════════════════════════════════════════════════════════
  //  Confirm-before-submit forms
  // ══════════════════════════════════════════════════════════
  function initConfirmForms() {
    document.addEventListener("submit", (e) => {
      const form = e.target.closest("[data-confirm]");
      if (!form) return;
      if (!window.confirm(form.dataset.confirm || "Are you sure?")) e.preventDefault();
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Daily reminder / Web Push notification settings
  // ══════════════════════════════════════════════════════════
  function initNotificationSettings() {
    const panel = $("#notifications");
    if (!panel) return; // push not configured server-side, or not on settings page

    const toggle = $("#reminderToggle", panel);
    const timeInput = $("#reminderTime", panel);
    const timeRow = $("#reminderTimeRow", panel);
    const statusText = $("#reminderStatusText", panel);
    const permissionNote = $("#reminderPermissionNote", panel);
    const vapidPublicKey = panel.dataset.vapidPublicKey;
    const csrfToken = panel.dataset.csrfToken;

    function urlBase64ToUint8Array(base64String) {
      const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
      const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
      const rawData = window.atob(base64);
      const outputArray = new Uint8Array(rawData.length);
      for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i);
      return outputArray;
    }

    function setUiState(enabled) {
      toggle.checked = enabled;
      statusText.textContent = enabled ? "On" : "Off";
      timeRow.style.opacity = enabled ? "1" : "0.5";
      timeInput.disabled = !enabled;
    }

    function saveReminderPrefs(enabled) {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const body = new URLSearchParams({
        csrf_token: csrfToken,
        reminder_enabled: enabled ? "true" : "false",
        reminder_time: timeInput.value || "20:00",
        reminder_timezone: timezone,
      });
      return fetch("/settings/notifications", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
    }

    async function enableReminders() {
      if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
        alert("This browser doesn't support notifications.");
        setUiState(false);
        return;
      }

      if (Notification.permission === "denied") {
        permissionNote.style.display = "block";
        setUiState(false);
        return;
      }

      let permission = Notification.permission;
      if (permission === "default") {
        permission = await Notification.requestPermission();
      }
      if (permission !== "granted") {
        permissionNote.style.display = "block";
        setUiState(false);
        return;
      }
      permissionNote.style.display = "none";

      try {
        const registration = await navigator.serviceWorker.register("/sw.js");
        await navigator.serviceWorker.ready;

        let subscription = await registration.pushManager.getSubscription();
        if (!subscription) {
          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
          });
        }

        await fetch("/api/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(subscription.toJSON()),
        });

        await saveReminderPrefs(true);
        setUiState(true);
      } catch (err) {
        console.error("Failed to enable reminders:", err);
        alert("Couldn't enable notifications. Please try again.");
        setUiState(false);
      }
    }

    async function disableReminders() {
      try {
        if ("serviceWorker" in navigator) {
          const registration = await navigator.serviceWorker.getRegistration("/sw.js");
          if (registration) {
            const subscription = await registration.pushManager.getSubscription();
            if (subscription) {
              await fetch("/api/push/unsubscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ endpoint: subscription.endpoint }),
              });
              await subscription.unsubscribe();
            }
          }
        }
      } catch (err) {
        console.error("Failed to unsubscribe cleanly:", err);
        // Still save the "off" preference server-side even if the browser-side
        // unsubscribe had trouble -- the scheduler checks reminder_enabled
        // first, so this alone stops future reminders regardless.
      }
      await saveReminderPrefs(false);
      setUiState(false);
    }

    toggle.addEventListener("change", () => {
      if (toggle.checked) {
        enableReminders();
      } else {
        disableReminders();
      }
    });

    timeInput.addEventListener("change", () => {
      if (toggle.checked) saveReminderPrefs(true);
    });

    // Initial UI state from what the server rendered (the DB's actual
    // reminder_enabled), not from browser subscription state -- those
    // two can legitimately disagree (e.g. site data cleared on this
    // device while still enabled on another), and the DB value is
    // what the scheduler actually acts on.
    setUiState(toggle.dataset.initial === "true");
  }

  // ══════════════════════════════════════════════════════════
  //  Delete-account confirmation modal
  //
  //  A native window.confirm() OK/Cancel takes one click and is easy to
  //  dismiss on reflex without reading it -- not enough friction for an
  //  action that permanently destroys every diary entry with no undo.
  //  Require typing the word DELETE (case-sensitive, exact match) before
  //  the actual delete button becomes clickable at all.
  // ══════════════════════════════════════════════════════════
  function initDeleteAccountModal() {
    const openBtn = $("#openDeleteAccountModal");
    const overlay = $("#deleteAccountOverlay");
    if (!openBtn || !overlay) return;

    const panel = $(".modal-panel", overlay);
    const input = $("#deleteAccountConfirmInput", overlay);
    const confirmBtn = $("#confirmDeleteAccount", overlay);
    const cancelBtn = $("#cancelDeleteAccount", overlay);
    const form = $("#deleteAccountForm");
    let lastFocused = null;

    function open() {
      lastFocused = document.activeElement;
      overlay.style.display = "flex";
      overlay.classList.add("open");
      overlay.setAttribute("aria-hidden", "false");
      input.value = "";
      confirmBtn.disabled = true;
      document.body.style.overflow = "hidden";
      setTimeout(() => input.focus(), 50);
    }

    function close() {
      overlay.classList.remove("open");
      overlay.setAttribute("aria-hidden", "true");
      overlay.style.display = "none";
      document.body.style.overflow = "";
      if (lastFocused) lastFocused.focus();
    }

    window.__openDeleteAccountModal = open;
    window.__closeDeleteAccountModal = close;

    // Focus trap: while this modal is open, Tab/Shift+Tab must cycle
    // only among its own focusable elements. Without this, focus can
    // walk right out onto sidebar links and other page content sitting
    // behind the visual backdrop -- still technically focusable, just
    // invisible and completely disorienting for a keyboard/screen-reader
    // user, and a real WAI-ARIA dialog-pattern violation for a modal
    // confirming a destructive, irreversible action.
    const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    panel.addEventListener("keydown", (e) => {
      if (e.key !== "Tab") return;
      const focusable = Array.from(panel.querySelectorAll(FOCUSABLE)).filter(
        (el) => !el.disabled && el.offsetParent !== null
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });

    openBtn.addEventListener("click", open);
    cancelBtn.addEventListener("click", close);

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay.classList.contains("open")) close();
    });

    function isDeleteMatch(val) {
      return val === 'DELETE';
    }

    input.addEventListener("input", () => {
      confirmBtn.disabled = !isDeleteMatch(input.value);
    });

    // Enter in the input submits as soon as it's valid, same as clicking
    // the button -- no reason to force a second click once they've typed it.
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !confirmBtn.disabled) {
        e.preventDefault();
        confirmBtn.click();
      }
    });

    confirmBtn.addEventListener("click", () => {
      if (!isDeleteMatch(input.value)) return;
      confirmBtn.disabled = true;
      confirmBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Deleting…';
      form.submit();
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Active sidebar nav link
  // ══════════════════════════════════════════════════════════
  function initActiveNav() {
    const path = window.location.pathname;
    const search = window.location.search;
    
    $$(".nav-link-side").forEach((link) => {
      const href = link.getAttribute("href");
      if (!href) return;
      
      const parts = href.split("?");
      const hrefPath = parts[0];
      const hrefSearch = parts[1] ? "?" + parts[1] : "";
      
      if (hrefSearch) {
        // If link expects specific search params, they must be present in window.location.search
        if (path === hrefPath && search.includes(hrefSearch.substring(1))) {
          link.classList.add("active");
        }
      } else {
        // No search params expected in link: match if path matches and no filters are on,
        // or if it is a sub-path of the link (like /diaries/new or /diaries/123)
        if (path === hrefPath && (!search || search === "?msg=" || search === "?err=")) {
          link.classList.add("active");
        } else if (hrefPath !== "/" && hrefPath !== "#" && path.startsWith(hrefPath) && path !== hrefPath) {
          // If we are on /diaries/new, do not highlight parent "/diaries" because "/diaries/new" has its own dedicated link
          if (hrefPath === "/diaries" && (path === "/diaries/new" || path.startsWith("/diaries/"))) {
             // For /diaries/new, we don't highlight /diaries. 
             // For /diaries/ID, we might want to highlight /diaries if there's no better match.
             // However, /diaries usually means the LIST.
             if (path === "/diaries/new") return;
             link.classList.add("active");
          } else {
            link.classList.add("active");
          }
        }
      }
    });
  }



  // ══════════════════════════════════════════════════════════
  //  Count-up animation for stat cards
  // ══════════════════════════════════════════════════════════
  function initCountUp() {
    const els = $$(".stat-value[data-count]");
    if (!els.length) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        const el     = entry.target;
        const target = parseInt(el.dataset.count, 10);
        const dur    = Math.min(1200, target * 25); // scale duration
        const start  = performance.now();

        function tick(now) {
          const elapsed = now - start;
          const progress = Math.min(elapsed / dur, 1);
          // ease-out
          const eased = 1 - Math.pow(1 - progress, 3);
          el.textContent = Math.round(eased * target).toLocaleString();
          if (progress < 1) requestAnimationFrame(tick);
        }

        requestAnimationFrame(tick);
      });
    }, { threshold: 0.4 });

    els.forEach((el) => observer.observe(el));
  }

  // ══════════════════════════════════════════════════════════
  //  Tag helper (add tag from suggestion)
  // ══════════════════════════════════════════════════════════
  window.addTag = (name) => {
    const input = document.getElementById("tagsInput");
    if (!input) return;
    const current = input.value.split(",").map((t) => t.trim()).filter(Boolean);
    if (!current.includes(name)) {
      current.push(name);
      input.value = current.join(", ");
      input.dispatchEvent(new Event("input"));
    }
  };

  // ══════════════════════════════════════════════════════════
  //  AJAX Toast — bottom-right pop-up feedback
  // ══════════════════════════════════════════════════════════
  function showToast(message, type = "success", durationMs = 3200) {
    const toast = document.createElement("div");
    toast.className = `ajax-toast ${type}`;

    const iconEl = document.createElement("span");
    iconEl.className = "ajax-toast-icon";
    iconEl.textContent = type === "success" ? "✓" : "✕";

    const msgEl = document.createElement("span");
    msgEl.className = "ajax-toast-msg";
    msgEl.textContent = message; // textContent, not innerHTML: avoids
                                  // breaking on/leaking arbitrary HTML in
                                  // user-controlled strings like filenames.

    toast.appendChild(iconEl);
    toast.appendChild(msgEl);
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.animation = "toastOut 0.3s var(--ease) both";
      toast.addEventListener("animationend", () => toast.remove(), { once: true });
    }, durationMs);
    return toast;
  }

  // ══════════════════════════════════════════════════════════
  //  Copy share link — uses the app's own toast, not alert()
  // ══════════════════════════════════════════════════════════
  function initCopyShareLink() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".copy-share-link-btn");
      if (!btn) return;
      const diaryId = btn.dataset.diaryId;
      const url = `${window.location.origin}/diaries/${diaryId}`;

      const done = () => showToast("Link copied to clipboard", "success", 2200);
      const failed = () => showToast("Couldn't copy link — please copy it manually", "error", 3200);

      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(url).then(done).catch(failed);
      } else {
        failed();
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  AJAX Toggle — favourite / pin / archive
  //  Usage: <button data-toggle-url="/diaries/ID/favorite"
  //                 data-toggle-flag="is_favorite"
  //                 data-active-class="btn-toggle-active"
  //                 data-icon-on="bi-star-fill"
  //                 data-icon-off="bi-star"
  //                 data-label-on="Unfavourite" data-label-off="Favourite">
  // ══════════════════════════════════════════════════════════
  function initAjaxToggles() {
    document.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-toggle-url]");
      if (!btn) return;
      e.preventDefault();

      if (btn.classList.contains("is-loading")) return;
      btn.classList.add("is-loading");

      const url   = btn.dataset.toggleUrl;
      const csrf  = document.querySelector('meta[name="csrf-token"]')?.content || "";

      try {
        const res  = await fetch(url, {
          method:  "POST",
          headers: {
            "X-Requested-With": "fetch",
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: `csrf_token=${encodeURIComponent(csrf)}`,
        });
        const data = await res.json();

        if (!data.ok) {
          showToast(data.detail || "Something went wrong", "error");
          return;
        }

        // Update button appearance
        const isOn        = data.value;
        const activeClass = btn.dataset.activeClass  || "btn-toggle-active";
        const iconOn      = btn.dataset.iconOn;
        const iconOff     = btn.dataset.iconOff;
        const labelOn     = btn.dataset.labelOn;
        const labelOff    = btn.dataset.labelOff;

        btn.classList.toggle(activeClass, isOn);
        btn.classList.remove("just-toggled");
        void btn.offsetWidth; // restart the animation even on rapid re-toggles
        btn.classList.add("just-toggled");
        setTimeout(() => btn.classList.remove("just-toggled"), 450);

        const iconEl = btn.querySelector("i");
        if (iconEl && iconOn && iconOff) {
          iconEl.className = `bi ${isOn ? iconOn : iconOff}`;
        }

        const labelEl = btn.querySelector(".toggle-label");
        if (labelEl && labelOn && labelOff) {
          labelEl.textContent = isOn ? labelOn : labelOff;
        }

        // Keep the accessible name (and tooltip) in sync even when the
        // visible text label is hidden by CSS on narrow screens.
        if (labelOn && labelOff) {
          const accessibleName = isOn ? labelOn : labelOff;
          btn.setAttribute("aria-label", accessibleName);
          btn.setAttribute("title", accessibleName);
        }

        // Also update any aria attributes
        btn.setAttribute("aria-pressed", isOn ? "true" : "false");

        if (btn.dataset.toggleFlag === "is_bookmarked") {
          const ribbon = document.getElementById("diaryRibbonBookmark");
          if (ribbon) {
            ribbon.classList.toggle("bookmarked", isOn);
            ribbon.setAttribute("title", isOn ? "Bookmarked entry — click to unbookmark" : "Click to bookmark this entry");
            ribbon.setAttribute("aria-pressed", isOn ? "true" : "false");
          }
        }

        const flagName = (btn.dataset.toggleFlag || "").replace("is_", "").replace("_", "-");
        const verb = isOn
          ? (flagName === "favorite" ? "Added to favourites" : flagName === "pinned" ? "Pinned" : flagName === "bookmarked" ? "Bookmarked" : "Archived")
          : (flagName === "favorite" ? "Removed from favourites" : flagName === "pinned" ? "Unpinned" : flagName === "bookmarked" ? "Removed bookmark" : "Restored");
        showToast(verb, "success", 2000);


      } catch (err) {
        showToast("Network error — please try again", "error");
      } finally {
        btn.classList.remove("is-loading");
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Auto-resize textarea (journal writing area)
  // ══════════════════════════════════════════════════════════
  function initAutoResize() {
    function resize(el) {
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }

    $$(".journal-textarea").forEach((ta) => {
      resize(ta); // initial
      ta.addEventListener("input", () => resize(ta));
      ta.addEventListener("focus", () => resize(ta));
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Ruled-paper line alignment
  //
  //  .diary-reading (view page) and .journal-textarea (edit page) both
  //  paint horizontal ruled lines as a repeating-linear-gradient
  //  background and need that pattern's vertical offset to land exactly
  //  on the real text baseline. A hardcoded em value for that offset
  //  only ever matches one specific font at one specific size — it
  //  silently drifts out of alignment the moment font-size shifts (this
  //  app uses clamp() for both, so it's *always* shifting across
  //  viewport widths), which is why this kept coming back. Measuring
  //  the actual baseline in the user's actual browser, live, removes
  //  the guesswork entirely: the offset is always correct because it's
  //  read from the real rendered line box, not assumed.
  // ══════════════════════════════════════════════════════════
  function initRuledLineAlignment() {
    // .turn-face is the sheet that's filled with real page text mid-flip;
    // it has its own ruled-line background, so it needs its own offset
    // (it isn't a descendant of .diary-reading, so it can't inherit one).
    const targets = $$(".diary-reading, .journal-textarea, .turn-face");
    if (!targets.length) return;

    // Classic baseline-detection trick: an inline-block span with
    // vertical-align:top marks the line box's own top edge; a second
    // zero-size span with vertical-align:baseline sits exactly on the
    // text baseline. The gap between their top edges, measured with
    // getBoundingClientRect (sub-pixel accurate, already accounts for
    // font hinting/metrics quirks per-browser), is the true
    // top-of-line-box → baseline distance for this font/size.
    function measureBaselineOffset(el) {
      const cs = getComputedStyle(el);
      const wrap = document.createElement("span");
      wrap.style.cssText =
        "position:absolute;left:-9999px;top:0;visibility:hidden;white-space:nowrap;" +
        "font-family:" + cs.fontFamily + ";" +
        "font-size:" + cs.fontSize + ";" +
        "font-weight:" + cs.fontWeight + ";" +
        "line-height:" + cs.lineHeight + ";" +
        "letter-spacing:" + cs.letterSpacing + ";";
      const topMark = document.createElement("span");
      topMark.style.cssText = "display:inline-block;width:0;height:0;vertical-align:top;";
      const baselineMark = document.createElement("span");
      baselineMark.style.cssText = "display:inline-block;width:0;height:0;vertical-align:baseline;";
      wrap.appendChild(topMark);
      wrap.appendChild(baselineMark);
      wrap.appendChild(document.createTextNode("Mg")); // real glyphs so metrics are real
      document.body.appendChild(wrap);
      const offset = baselineMark.getBoundingClientRect().top - topMark.getBoundingClientRect().top;
      document.body.removeChild(wrap);
      return offset;
    }

    // How far below the text baseline the ruled line's bottom edge
    // sits. 2px puts the 1px line just under the letters' feet, the way
    // handwriting sits on ruled paper (descenders still drop through it).
    const RULE_DROP = 2;

    function align() {
      targets.forEach((el) => {
        const offset = measureBaselineOffset(el);
        if (!(offset > 0)) return;
        const cs = getComputedStyle(el);
        const lineHeight = parseFloat(cs.lineHeight);
        if (!(lineHeight > 0)) return;
        // measureBaselineOffset() is "top of the line box -> baseline".
        // But background-position-y is measured from the top of the
        // *padding box*, and the first line box starts paddingTop below
        // that -- this used to hand the raw offset straight to CSS, so
        // every ruled line landed paddingTop (12px on the reading page)
        // too high and cut through the lettering instead of running
        // under it.
        const paddingTop = parseFloat(cs.paddingTop) || 0;
        const firstRuleBottom = paddingTop + offset + RULE_DROP;
        // The gradient draws each 1px line at the *bottom* of its
        // period, so tile k's line ends at pos + (k+1)*lineHeight.
        // Normalise into (-lineHeight, 0]: same phase, but keeps the
        // tile seam outside the visible box at the top.
        const pos = (firstRuleBottom % lineHeight) - lineHeight;
        el.style.setProperty("--rule-offset", pos.toFixed(2) + "px");
      });
    }

    let resizeTimer;
    align();
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(align, 150);
    }, { passive: true });
    // Web fonts (Lora / Caveat) can finish loading after first paint,
    // which changes the real metrics out from under an earlier measurement.
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(align);
    }
  }

  // ══════════════════════════════════════════════════════════
  //  AJAX File Upload — drag-drop zone with progress
  // ══════════════════════════════════════════════════════════
  function initAjaxUpload() {
    const zone     = document.getElementById("uploadZone");
    const fileInput= document.getElementById("attachmentFile");
    const uploadBtn= document.getElementById("uploadBtn");
    const progressBar   = document.getElementById("uploadProgressBar");
    const progressFill  = document.getElementById("uploadProgressFill");
    const uploadStatus  = document.getElementById("uploadStatus");
    const attList       = document.getElementById("attachmentList");
    const attEmpty      = document.getElementById("attachmentEmpty");

    if (!zone || !fileInput) return;

    const DIARY_ID = zone.dataset.diaryId;
    const CSRF     = document.querySelector('meta[name="csrf-token"]')?.content || "";

    // Click zone to open file picker
    zone.addEventListener("click", (e) => {
      if (e.target !== uploadBtn && !e.target.closest("#uploadBtn")) {
        fileInput.click();
      }
    });

    // Drag-and-drop
    ["dragenter","dragover"].forEach(ev =>
      zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("dragover"); })
    );
    ["dragleave","drop"].forEach(ev =>
      zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("dragover"); })
    );
    zone.addEventListener("drop", (e) => {
      const files = e.dataTransfer?.files;
      if (files?.length) {
        fileInput.files = files;
        handleUpload(files[0]);
      }
    });

    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) handleUpload(fileInput.files[0]);
    });

    // Upload button explicit click
    uploadBtn?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!fileInput.files || !fileInput.files.length) {
        // The button is the zone's keyboard-reachable control, so with no
        // file chosen it opens the picker (choosing a file uploads it).
        fileInput.click();
        return;
      }
      handleUpload(fileInput.files[0]);
    });

    function handleUpload(file) {
      zone.classList.add("uploading");
      progressBar?.classList.add("active");
      if (uploadStatus) uploadStatus.textContent = `Uploading ${file.name}…`;

      const formData = new FormData();
      formData.append("file", file);
      formData.append("csrf_token", CSRF);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/diaries/${DIARY_ID}/attachments`);
      xhr.setRequestHeader("X-Requested-With", "fetch");

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && progressFill) {
          progressFill.style.width = Math.round((e.loaded / e.total) * 100) + "%";
        }
      };

      xhr.onload = () => {
        zone.classList.remove("uploading");
        progressBar?.classList.remove("active");
        if (progressFill) progressFill.style.width = "0%";
        fileInput.value = "";

        let data;
        try { data = JSON.parse(xhr.responseText); } catch { data = { ok: false, detail: "Unexpected response" }; }

        if (data.ok && data.attachment) {
          appendAttachment(data.attachment);
          if (uploadStatus) uploadStatus.textContent = "";
          showToast(`${data.attachment.filename} uploaded!`, "success");
        } else {
          if (uploadStatus) uploadStatus.textContent = "";
          showToast(data.detail || "Upload failed", "error");
        }
      };

      xhr.onerror = () => {
        zone.classList.remove("uploading");
        progressBar?.classList.remove("active");
        showToast("Network error during upload", "error");
      };

      xhr.send(formData);
    }

    function appendAttachment(att) {
      if (attEmpty) attEmpty.style.display = "none";
      if (!attList) return;

      const kb = (att.size / 1024).toFixed(1);
      let icon = "bi-file-earmark-text-fill";
      if (att.mime_type?.startsWith("image/")) icon = "bi-image-fill";
      else if (att.mime_type === "application/pdf") icon = "bi-file-pdf-fill";

      // Built with createElement/textContent rather than one big
      // innerHTML template string -- att.filename is the visitor's own
      // upload filename (attacker-controlled, in principle: nothing
      // stops someone naming a file <img src=x onerror=...>), and this
      // runs right after their own upload. showToast() a few lines up
      // already treats filenames this carefully; this just brings
      // appendAttachment() in line with that.
      const item = document.createElement("div");
      item.className = "attachment-item";
      item.dataset.attachmentId = att.id;
      item.style.marginBottom = ".5rem";
      item.style.animation = "scaleIn .3s var(--ease-spring) both";

      const iconEl = document.createElement("i");
      iconEl.className = `bi ${icon} attachment-icon`;
      iconEl.setAttribute("aria-hidden", "true");

      const meta = document.createElement("div");
      meta.style.cssText = "flex:1;min-width:0;";
      const nameEl = document.createElement("div");
      nameEl.style.cssText = "font-weight:600;font-size:.85rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
      nameEl.textContent = att.filename;
      const sizeEl = document.createElement("div");
      sizeEl.style.cssText = "font-size:.72rem;color:var(--txt-muted);";
      sizeEl.textContent = `${kb} KB · ${att.mime_type || ""}`;
      meta.append(nameEl, sizeEl);

      const actions = document.createElement("div");
      actions.className = "att-actions";

      const dlLink = document.createElement("a");
      dlLink.href = `/attachments/${att.id}/download`;
      dlLink.className = "btn btn-surface btn-sm att-download-btn";
      dlLink.setAttribute("download", "");
      dlLink.dataset.filename = att.filename;
      dlLink.style.cssText = "padding:.3rem .5rem;min-height:unset;height:auto;";
      dlLink.title = `Download ${att.filename}`;
      dlLink.setAttribute("aria-label", `Download ${att.filename}`);
      const dlIcon = document.createElement("i");
      dlIcon.className = "bi bi-download";
      dlIcon.setAttribute("aria-hidden", "true");
      dlLink.appendChild(dlIcon);

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn btn-outline-danger btn-sm att-delete-btn";
      delBtn.dataset.attachmentId = att.id;
      delBtn.dataset.filename = att.filename;
      delBtn.style.cssText = "padding:.3rem .5rem;min-height:unset;height:auto;";
      delBtn.title = `Delete ${att.filename}`;
      delBtn.setAttribute("aria-label", `Delete ${att.filename}`);
      const delIcon = document.createElement("i");
      delIcon.className = "bi bi-trash3-fill";
      delIcon.setAttribute("aria-hidden", "true");
      delBtn.appendChild(delIcon);

      actions.append(dlLink, delBtn);
      item.append(iconEl, meta, actions);
      attList.appendChild(item);
      updateAttachmentCount(1);
    }

    function updateAttachmentCount(delta) {
      const countEl = document.querySelector("#attachmentList")?.closest(".card")?.querySelector(".card-header span");
      if (!countEl) return;
      const match = countEl.textContent.match(/-?\d+/);
      const current = match ? parseInt(match[0], 10) : 0;
      countEl.textContent = `(${Math.max(0, current + delta)})`;
    }

    // Delete an attachment (event-delegated so it works for both
    // server-rendered and AJAX-appended items)
    attList?.addEventListener("click", (e) => {
      const btn = e.target.closest(".att-delete-btn");
      if (!btn) return;

      const id = btn.dataset.attachmentId;
      const filename = btn.dataset.filename || "this file";
      if (!window.confirm(`Delete "${filename}"? This cannot be undone.`)) return;

      const item = btn.closest(".attachment-item");
      btn.disabled = true;

      fetch(`/api/attachments/${id}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": CSRF, "X-Requested-With": "fetch" },
      })
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (ok) {
            item?.remove();
            updateAttachmentCount(-1);
            showToast(`${filename} deleted`, "success");
            if (attList && attList.children.length === 0 && attEmpty) {
              attEmpty.style.display = "";
            }
          } else {
            btn.disabled = false;
            showToast(data?.detail || "Couldn't delete attachment", "error");
          }
        })
        .catch(() => {
          btn.disabled = false;
          showToast("Network error while deleting attachment", "error");
        });
    });
  }

  // ══════════════════════════════════════════════════════════
  //  Attachment download progress
  // ══════════════════════════════════════════════════════════
  // A plain <a download> gives no feedback at all while it's in flight
  // -- the browser's own download indicator lives outside the page,
  // and most attachments here are small enough that "nothing visibly
  // happens" reads as normal right up until it doesn't. This streams
  // the response instead so a real progress bar can track bytes-
  // received against Content-Length (which the download route already
  // sends via FileResponse), then assembles the bytes into a Blob and
  // triggers the actual save. Falls back to a plain navigation on any
  // failure -- enhancement, not a hard dependency.
  //
  // Deliberately its own top-level init, not folded into
  // initAjaxUpload(): that function returns early when #uploadZone
  // isn't on the page, which is exactly the case for a public/shared
  // viewer who can still see a Download button but never an upload
  // dropzone. Nesting this in there would have quietly disabled
  // download progress for every non-owner viewer.
  function initDownloadProgress() {
    document.addEventListener("click", (e) => {
      const link = e.target.closest(".att-download-btn");
      if (!link || link.dataset.downloading === "1") return;
      if (!window.fetch || !window.ReadableStream) return; // let the native <a download> handle it
      e.preventDefault();
      downloadWithProgress(link);
    });
  }

  function downloadWithProgress(link) {
    const url = link.getAttribute("href");
    const filename = link.dataset.filename || "download";
    link.dataset.downloading = "1";

    let bar = link.nextElementSibling;
    if (!bar || !bar.classList.contains("dl-progress-bar")) {
      bar = document.createElement("div");
      bar.className = "dl-progress-bar";
      const fillEl = document.createElement("div");
      fillEl.className = "dl-progress-fill";
      bar.appendChild(fillEl);
      link.insertAdjacentElement("afterend", bar);
    }
    const fill = bar.querySelector(".dl-progress-fill");
    bar.classList.add("active");
    fill.style.width = "0%";

    const finish = () => {
      delete link.dataset.downloading;
      bar.classList.remove("active");
      fill.style.width = "0%";
    };

    fetch(url)
      .then((resp) => {
        if (!resp.ok || !resp.body) throw new Error("download response not ok");
        const total = Number(resp.headers.get("Content-Length")) || 0;
        const reader = resp.body.getReader();
        const chunks = [];
        let loaded = 0;

        function pump() {
          return reader.read().then(({ done, value }) => {
            if (done) return;
            chunks.push(value);
            loaded += value.length;
            if (total > 0) {
              fill.style.width = Math.min(100, Math.round((loaded / total) * 100)) + "%";
            }
            return pump();
          });
        }

        return pump().then(() => {
          fill.style.width = "100%";
          const blob = new Blob(chunks, { type: resp.headers.get("Content-Type") || "application/octet-stream" });
          const blobUrl = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = blobUrl;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(blobUrl), 4000);
        });
      })
      .catch(() => {
        showToast("Couldn't show download progress — downloading normally…", "error", 2500);
        window.location.href = url;
      })
      .finally(finish);
  }

  // ══════════════════════════════════════════════════════════
  //  Mood pill selector (new compact toolbar version)
  // ══════════════════════════════════════════════════════════
  function initMoodPills() {
    const pills   = $$(".mood-pill");
    const hidden  = document.getElementById("moodInput");
    if (!pills.length || !hidden) return;

    pills.forEach(pill => {
      pill.addEventListener("click", () => {
        pills.forEach(p => p.classList.remove("selected"));
        pill.classList.add("selected");
        hidden.value = pill.dataset.mood;
        // animate bounce
        pill.style.animation = "none";
        pill.offsetHeight; // reflow
        pill.style.animation = "moodBounce .4s var(--ease-spring) both";
      });
    });

    // Set initial selected state
    const currentMood = hidden.value;
    if (currentMood) {
      const match = pills.find(p => p.dataset.mood === currentMood);
      if (match) match.classList.add("selected");
    }
  }

  // ══════════════════════════════════════════════════════════
  //  Init all
  // ══════════════════════════════════════════════════════════
  initTheme();

  document.addEventListener("DOMContentLoaded", () => {
    initRipple();
    initSidebar();
    initIsland();
    initFlash();
    initCopyShareLink();
    initPasswordToggle();
    initPasswordStrength();
    initRegisterForm();
    initLoginForm();
    initForgotPasswordForm();
    initResetPasswordForm();
    initMoodSelector();
    initMoodPills();
    initTagInput();
    initWordCount();
    initTitleCounter();
    initAutosave();
    initDiaryFormValidation();
    initSettingsValidation();
    initSettingsTabs();
    initConfirmForms();
    initDeleteAccountModal();
    initNotificationSettings();
    initActiveNav();
    initCountUp();
    initAjaxToggles();
    initAutoResize();
    initAjaxUpload();
    initDownloadProgress();

  // ════════════════════════════════════════════════════════════
  //  Diary Book Container & 3D Page Turn Engine
  // ════════════════════════════════════════════════════════════
  function initDiaryBookPaging() {
    const container = document.getElementById("journalBookContainer");
    const pageCard = document.getElementById("journalPageCard");
    const rawContent = document.getElementById("diaryContentRaw");
    if (!container || !pageCard || !rawContent) return;

    const viewport = document.getElementById("journalReadingViewport");
    const readingArea = document.getElementById("diaryReading");
    const attachments = document.getElementById("diaryAttachmentsBlock");
    const btnPrev = document.getElementById("btnBookPrev");
    const btnNext = document.getElementById("btnBookNext");
    const pageText = document.getElementById("bookPageText");
    const cornerPrev = document.getElementById("cornerPrevBtn");
    const cornerNext = document.getElementById("cornerNextBtn");
    const btnToggleView = document.getElementById("btnBookToggleView");
    const viewToggleLabel = document.getElementById("viewToggleLabel");
    const overlay = document.getElementById("pageTurnOverlay");
    const sheet = document.getElementById("pageTurnSheet");
    const turnFront = document.getElementById("turnFaceFront");
    const turnBack = document.getElementById("turnFaceBack");
    const endFlourish = document.getElementById("diaryEndFlourish");

    // Interactive Silk Ribbon Bookmark
    const ribbon = document.getElementById("diaryRibbonBookmark");
    if (ribbon) {
      ribbon.addEventListener("click", () => {
        const bkmkBtn = document.querySelector('button[data-toggle-flag="is_bookmarked"]');
        if (bkmkBtn) bkmkBtn.click();
      });
      ribbon.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          const bkmkBtn = document.querySelector('button[data-toggle-flag="is_bookmarked"]');
          if (bkmkBtn) bkmkBtn.click();
        }
      });
    }

    let isContinuous = true;
    let isFlipping = false;
    let currentPage = 1;
    let pages = [];

    const fullText = (rawContent.textContent || "").trim();

    // ── Pagination by measurement ──────────────────────────────────────
    // Pages used to be sized by a hardcoded budget (280 words / 1700
    // chars, 180 / 1000 on phones) that had nothing to do with how much
    // text the book-view viewport can actually show: it's clipped to
    // clamp(520px, 72vh, 760px) with overflow:hidden, and the handwriting
    // font sets ~43px lines, so roughly 14 lines fit -- about half what a
    // "page" was allowed to hold. Every page overflowed its clip box and
    // its last lines were cut off, and since the next page starts where
    // *this* function stopped, those lines were never shown anywhere.
    // Now each page is packed word by word into an off-screen copy of the
    // text element until its real rendered height reaches the viewport's
    // capacity, so it adapts to font, line-height, width and window size.
    let lastLayoutKey = "";

    // Pixel height of text one book page can show, plus a key describing
    // everything that capacity depends on (so resize can skip no-ops).
    //
    // Measured, not read from CSS: the viewport's max-height
    // (clamp(520px, 72vh, 760px)) is only an upper bound. On a phone the
    // page card constrains the viewport much further (header + nav take
    // most of the screen: 311px of a 608px max-height at 390x844), so
    // trusting max-height put ~2x too much text on every page. Instead,
    // briefly fill the page with far more text than could fit and see how
    // tall the viewport really ends up. All synchronous: nothing paints.
    function pageCapacity() {
      const saved = {
        text: rawContent.textContent,
        rawDisplay: rawContent.style.display,
        flourish: endFlourish ? endFlourish.style.display : "",
        attachments: attachments ? attachments.style.display : "",
      };
      const wasContinuous = pageCard.classList.contains("continuous-view");
      if (wasContinuous) pageCard.classList.remove("continuous-view");
      rawContent.style.display = "block";
      rawContent.textContent = new Array(400).join("x\n");   // ~17000px: more than any page holds
      if (endFlourish) endFlourish.style.display = "none";
      if (attachments) attachments.style.display = "none";

      const vpHeight = viewport ? viewport.getBoundingClientRect().height : window.innerHeight * 0.72;
      const cs = getComputedStyle(readingArea || rawContent);
      const padTop = parseFloat(cs.paddingTop) || 0;
      const padX = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
      const width = (readingArea ? readingArea.clientWidth : rawContent.clientWidth) - padX;
      const fontKey = cs.fontSize + "|" + cs.lineHeight;

      rawContent.textContent = saved.text;
      rawContent.style.display = saved.rawDisplay;
      if (endFlourish) endFlourish.style.display = saved.flourish;
      if (attachments) attachments.style.display = saved.attachments;
      if (wasContinuous) pageCard.classList.add("continuous-view");

      // bottom padding is allowed to be clipped, top padding is not
      const capacity = vpHeight - padTop;
      return { capacity, width, key: [Math.round(capacity), Math.round(width), fontKey].join("|") };
    }

    // Height of an element that is normally display:none or hidden.
    function outerHeightOf(el) {
      if (!el) return 0;
      const prev = el.style.display;
      el.style.display = el.id === "diaryEndFlourish" ? "flex" : "block";
      const h = el.getBoundingClientRect().height + (parseFloat(getComputedStyle(el).marginTop) || 0);
      el.style.display = prev;
      return h;
    }

    function paginate() {
      pages = [];
      if (!fullText) {
        pages.push({ text: "", startChar: 0, hasAttachments: !!attachments });
        return;
      }
      const { capacity, width, key } = pageCapacity();
      lastLayoutKey = key;

      // Off-screen twin of #diaryContentRaw (same classes => same
      // white-space, font, line-height) used only to measure heights.
      const measurer = document.createElement("div");
      measurer.className = rawContent.className;
      measurer.setAttribute("aria-hidden", "true");
      measurer.style.cssText = "position:absolute;visibility:hidden;pointer-events:none;left:0;top:0;width:" + width + "px;";
      (readingArea || rawContent.parentNode).appendChild(measurer);

      try {
        // Alternating [word, whitespace, word, ...]; keeps newlines intact.
        const tokens = fullText.split(/(\s+)/);
        const n = tokens.length;
        const offsets = new Array(n + 1);
        offsets[0] = 0;
        for (let i = 0; i < n; i++) offsets[i + 1] = offsets[i] + tokens[i].length;
        const isSpace = (t) => /^\s+$/.test(t);

        const heightOf = (a, b) => {
          measurer.textContent = tokens.slice(a, b).join("").trimEnd();
          return measurer.offsetHeight;
        };

        // Largest `end` (exclusive) such that tokens[start..end) fits `cap`.
        // One token always counts as fitting so every page makes progress.
        let lastSize = 200;
        const fitEnd = (start, cap) => {
          let lo = start + 1;
          let hi = Math.min(n, start + Math.max(8, lastSize));
          while (true) {
            if (heightOf(start, hi) <= cap) {
              lo = hi;
              if (hi >= n) return n;
              hi = Math.min(n, start + (hi - start) * 2);
            } else break;
          }
          while (hi - lo > 1) {
            const mid = (lo + hi) >> 1;
            if (heightOf(start, mid) <= cap) lo = mid; else hi = mid;
          }
          lastSize = lo - start;
          return lo;
        };

        const pack = (from, cap) => {
          const out = [];
          let start = from;
          while (start < n) {
            while (start < n && isSpace(tokens[start])) start++;   // no blank lines at a page top
            if (start >= n) break;
            const end = fitEnd(start, cap);
            out.push({ text: tokens.slice(start, end).join("").trim(), startChar: offsets[start], _a: start, _b: end });
            start = end;
          }
          return out;
        };

        let built = pack(0, capacity);
        if (built.length === 0) built = [{ text: fullText, startChar: 0, _a: 0, _b: n }];

        // The last text page also has to hold the end flourish, so if it
        // doesn't fit there, repack just that tail with less room.
        const flourishH = outerHeightOf(endFlourish);
        const last = built[built.length - 1];
        if (heightOf(last._a, last._b) + flourishH > capacity) {
          built = built.slice(0, -1).concat(pack(last._a, Math.max(capacity - flourishH, 0)));
        }

        // Attachments ride along on the last text page only if they fit
        // under the text + flourish; otherwise they get their own page.
        let attachmentsOnLast = false;
        if (attachments) {
          const l = built[built.length - 1];
          attachmentsOnLast = heightOf(l._a, l._b) + flourishH + outerHeightOf(attachments) <= capacity;
        }
        pages = built.map((pg, i) => ({
          text: pg.text, startChar: pg.startChar,
          hasAttachments: !!attachments && attachmentsOnLast && i === built.length - 1,
        }));
        if (attachments && !attachmentsOnLast) {
          pages.push({ text: "", startChar: fullText.length, hasAttachments: true });
        }
      } finally {
        measurer.remove();
      }
    }

    // Re-flow when the thing the pages were measured against changes:
    // window size / rotation, and the moment the handwriting font actually
    // loads (the first measurement may have used the fallback font).
    function repaginate() {
      if (isContinuous) return;
      if (isFlipping) { clearTimeout(repaginateTimer); repaginateTimer = setTimeout(repaginate, 200); return; }
      if (pageCapacity().key === lastLayoutKey) return;
      const keep = pages[currentPage - 1] ? pages[currentPage - 1].startChar : 0;
      paginate();
      let idx = 0;
      for (let i = 0; i < pages.length; i++) if (pages[i].startChar <= keep) idx = i;
      renderPage(idx + 1);
    }
    let repaginateTimer;
    window.addEventListener("resize", () => {
      clearTimeout(repaginateTimer);
      repaginateTimer = setTimeout(repaginate, 150);
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(repaginate);

    function renderPage(pageNum) {
      if (pageNum < 1) pageNum = 1;
      if (pageNum > pages.length) pageNum = pages.length;
      currentPage = pageNum;

      const pageData = pages[currentPage - 1];
      rawContent.textContent = pageData.text;
      rawContent.style.display = pageData.text ? "block" : "none";

      if (attachments) {
        attachments.style.display = pageData.hasAttachments ? "block" : "none";
      }

      if (pageText) pageText.textContent = "Page " + currentPage + " of " + pages.length;
      if (btnPrev) btnPrev.disabled = (currentPage === 1);
      if (btnNext) btnNext.disabled = (currentPage === pages.length);

      // The "end of entry" flourish is static HTML, rendered once
      // right after the content -- nothing was hiding it on any page
      // but the actual last one, so a multi-page book view showed a
      // "the end" decoration after page 1, page 2, every page, not
      // just the final one.
      if (endFlourish) endFlourish.style.display = (currentPage === pages.length) ? "" : "none";

      if (cornerPrev) cornerPrev.style.display = (currentPage > 1 && !isContinuous) ? "block" : "none";
      if (cornerNext) cornerNext.style.display = (currentPage < pages.length && !isContinuous) ? "block" : "none";

      if (readingArea) readingArea.scrollTop = 0;

      // Safety net: text pages are packed to fit, but a page can still be
      // taller than the viewport (e.g. the attachments page on a phone,
      // where the cards stack taller than the space the card leaves).
      // The viewport is overflow:hidden for the flip, which would just
      // cut that content off with no way to reach it -- let it scroll.
      if (viewport) {
        viewport.style.overflowY = "";
        viewport.scrollTop = 0;
        // Compare the lowest *visible element* with the clip edge rather
        // than scrollHeight: that includes the article's bottom padding,
        // which pages are deliberately allowed to run into.
        let lowest = -Infinity;
        [rawContent, endFlourish, attachments].forEach((el) => {
          if (el && el.style.display !== "none") lowest = Math.max(lowest, el.getBoundingClientRect().bottom);
        });
        if (lowest > viewport.getBoundingClientRect().bottom + 1) viewport.style.overflowY = "auto";
      }
    }

    function turnPage(direction) {
      if (isFlipping || isContinuous) return;
      const targetPage = direction === "next" ? currentPage + 1 : currentPage - 1;
      if (targetPage < 1 || targetPage > pages.length) return;

      // No flip for people who asked for less motion. The CSS only shortens
      // the animation to ~0, which left the sheet snapped to its end state
      // (showing the *next* page's text) for ~160ms, then removed it ~30ms
      // before the page underneath was swapped: next page -> old page ->
      // next page. Skip the overlay and swap at once.
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        renderPage(targetPage);
        return;
      }

      isFlipping = true;

      // Prepare 3D turning faces
      const curData = pages[currentPage - 1];
      const targetData = pages[targetPage - 1];

      if (turnFront) turnFront.textContent = curData.text;
      if (turnBack) turnBack.textContent = targetData.text;

      if (overlay) overlay.classList.add("flipping");
      if (sheet) {
        sheet.classList.remove("flip-forward", "flip-backward");
        void sheet.offsetWidth; // Force reflow
        sheet.classList.add(direction === "next" ? "flip-forward" : "flip-backward");
      }

      // Update actual page content underneath halfway through
      setTimeout(() => {
        renderPage(targetPage);
      }, 190);

      const safetyTimer = setTimeout(() => {
        onEnd();
      }, 420);

      const onEnd = () => {
        clearTimeout(safetyTimer);
        sheet?.removeEventListener("animationend", onEnd);
        if (overlay) overlay.classList.remove("flipping");
        if (sheet) sheet.classList.remove("flip-forward", "flip-backward");
        isFlipping = false;
      };
      if (sheet) sheet.addEventListener("animationend", onEnd, { once: true });
    }

    btnNext?.addEventListener("click", () => turnPage("next"));
    btnPrev?.addEventListener("click", () => turnPage("prev"));
    cornerNext?.addEventListener("click", () => turnPage("next"));
    cornerPrev?.addEventListener("click", () => turnPage("prev"));

    window.addEventListener("keydown", (e) => {
      if (isContinuous) return;
      // Leave every browser/OS shortcut and every control that uses the arrows
      // itself alone. Alt+Left is "Back" and Ctrl/Cmd+Arrow move by word or
      // line; swallowing them (preventDefault) broke those, and the <select> in
      // the share form lost its own Left/Right.
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (e.target.closest && e.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="dialog"], [role="alertdialog"], [role="slider"]')) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        turnPage("next");
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        turnPage("prev");
      }
    });

    let touchStartX = 0;
    let touchStartY = 0;
    viewport?.addEventListener("touchstart", (e) => {
      touchStartX = e.changedTouches[0].screenX;
      touchStartY = e.changedTouches[0].screenY;
    }, { passive: true });

    viewport?.addEventListener("touchend", (e) => {
      if (isContinuous) return;
      const diffX = e.changedTouches[0].screenX - touchStartX;
      const diffY = e.changedTouches[0].screenY - touchStartY;
      if (Math.abs(diffX) > 40 && Math.abs(diffY) < 55) {
        if (diffX < 0) turnPage("next");
        else turnPage("prev");
      }
    }, { passive: true });

    btnToggleView?.addEventListener("click", () => {
      isContinuous = !isContinuous;
      if (isContinuous) {
        pageCard.classList.add("continuous-view");
        rawContent.textContent = fullText;
        rawContent.style.display = "block";
        if (attachments) attachments.style.display = "block";
        if (btnPrev) btnPrev.style.display = "none";
        if (btnNext) btnNext.style.display = "none";
        if (pageText) pageText.textContent = "Continuous View";
        if (viewToggleLabel) viewToggleLabel.textContent = "Book View";
        if (cornerPrev) cornerPrev.style.display = "none";
        if (cornerNext) cornerNext.style.display = "none";
        if (endFlourish) endFlourish.style.display = "";
        if (viewport) { viewport.style.overflowY = ""; viewport.scrollTop = 0; }   // undo renderPage's tall-page scroll
      } else {
        pageCard.classList.remove("continuous-view");
        if (btnPrev) btnPrev.style.display = "";
        if (btnNext) btnNext.style.display = "";
        if (viewToggleLabel) viewToggleLabel.textContent = "Continuous View";
        paginate();
        renderPage(1);
      }
    });

    // Initial display: natural continuous journal view
    pageCard.classList.add("continuous-view");
    rawContent.textContent = fullText;
    rawContent.style.display = "block";
    if (attachments) attachments.style.display = "block";
    if (btnPrev) btnPrev.style.display = "none";
    if (btnNext) btnNext.style.display = "none";
    if (pageText) pageText.textContent = "Continuous View";
    if (viewToggleLabel) viewToggleLabel.textContent = "Book View";
    if (cornerPrev) cornerPrev.style.display = "none";
    if (cornerNext) cornerNext.style.display = "none";
    if (endFlourish) endFlourish.style.display = "";
  }

    initRuledLineAlignment();
    initDiaryBookPaging();
  });
})();

