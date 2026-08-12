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
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
    $$(".theme-toggle").forEach((btn) => {
      const icon = btn.querySelector("i");
      const label = btn.querySelector(".theme-label");
      if (icon) icon.className = theme === "dark" ? "bi bi-sun-fill" : "bi bi-moon-fill";
      if (label) label.textContent = theme === "dark" ? "Light" : "Dark";
    });
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
  function initSidebar() {
    const toggle = $("#sidebarToggle");
    const sidebar = $("#appSidebar");
    const overlay = $("#sidebarOverlay");
    if (!toggle || !sidebar) return;

    toggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
      overlay?.classList.toggle("open");
      toggle.setAttribute("aria-expanded", sidebar.classList.contains("open"));
    });

    overlay?.addEventListener("click", closeSidebar);

    function closeSidebar() {
      sidebar.classList.remove("open");
      overlay?.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }

    // Swipe left to close on mobile
    let touchStartX = 0;
    sidebar.addEventListener("touchstart", (e) => { touchStartX = e.changedTouches[0].screenX; }, { passive: true });
    sidebar.addEventListener("touchend", (e) => {
      if (touchStartX - e.changedTouches[0].screenX > 60) closeSidebar();
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

  function initPasswordStrength() {
    const pwInput = document.getElementById("reg-password");
    const fill = document.getElementById("pwStrengthFill");
    const label = document.getElementById("pwStrengthLabel");
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
        label.style.color = getStrengthColor(score);
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

      // Also trigger confirm match if filled
      const confirm = document.getElementById("reg-confirm");
      if (confirm && confirm.value) validateConfirmPassword();
    });
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
  //  Topbar search live submit on Enter
  // ══════════════════════════════════════════════════════════
  function initTopbarSearch() {
    const form = document.getElementById("topbarSearchForm");
    form?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); form.submit(); }
    });
  }

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
        showToast("Please choose a file first", "error", 3000);
        zone.classList.add("shake");
        zone.addEventListener("animationend", () => zone.classList.remove("shake"), { once: true });
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

      const item = document.createElement("div");
      item.className = "attachment-item";
      item.dataset.attachmentId = att.id;
      item.style.marginBottom = ".5rem";
      item.style.animation = "scaleIn .3s var(--ease-spring) both";
      item.innerHTML = `
        <i class="bi ${icon} attachment-icon" aria-hidden="true"></i>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:.85rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${att.filename}</div>
          <div style="font-size:.72rem;color:var(--txt-muted);">${kb} KB · ${att.mime_type || ""}</div>
        </div>
        <div class="att-actions">
          <a href="/attachments/${att.id}/download" class="btn btn-surface btn-sm" style="padding:.3rem .5rem;min-height:unset;height:auto;" title="Download ${att.filename}" aria-label="Download ${att.filename}" download>
            <i class="bi bi-download" aria-hidden="true"></i>
          </a>
          <button type="button" class="btn btn-outline-danger btn-sm att-delete-btn" data-attachment-id="${att.id}" data-filename="${att.filename}" style="padding:.3rem .5rem;min-height:unset;height:auto;" title="Delete ${att.filename}" aria-label="Delete ${att.filename}">
            <i class="bi bi-trash3-fill" aria-hidden="true"></i>
          </button>
        </div>`;
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
    initActiveNav();
    initCountUp();
    initTopbarSearch();
    initAjaxToggles();
    initAutoResize();
    initAjaxUpload();
  });
})();

