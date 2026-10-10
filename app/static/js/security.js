/* Second step (PIN / fingerprint / face) and recovery. Passkeys are WebAuthn platform authenticators:
   the browser asks the OS for the fingerprint or face; this script only shuttles the ceremony
   between the OS and the server. Every page that uses it also works without it (the PIN forms
   are ordinary forms), and the passkey buttons stay hidden unless the device offers a sensor. */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  const b64uToBuf = (s) => {
    s = s.replace(/-/g, "+").replace(/_/g, "/");
    const bin = atob(s + "=".repeat((4 - (s.length % 4)) % 4));
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out.buffer;
  };
  const bufToB64u = (buf) => {
    let s = "";
    for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };
  const csrf = () => {
    const m = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  };
  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
    return { ok: res.ok && data.ok !== false, status: res.status, data };
  }
  function say(msg, bad) {
    const el = $("#secMsg");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = bad ? "var(--danger-text)" : "var(--success-text)";
  }
  const supported = async () => {
    try {
      return !!(window.PublicKeyCredential && (await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()));
    } catch (e) {
      return false;
    }
  };

  const toCreate = (o) => {
    o.challenge = b64uToBuf(o.challenge);
    o.user.id = b64uToBuf(o.user.id);
    (o.excludeCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
    return o;
  };
  const toGet = (o) => {
    o.challenge = b64uToBuf(o.challenge);
    (o.allowCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
    return o;
  };
  const attestationJSON = (c) => ({
    id: c.id,
    rawId: bufToB64u(c.rawId),
    type: c.type,
    authenticatorAttachment: c.authenticatorAttachment || undefined,
    clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
    response: {
      clientDataJSON: bufToB64u(c.response.clientDataJSON),
      attestationObject: bufToB64u(c.response.attestationObject),
      transports: c.response.getTransports ? c.response.getTransports() : [],
    },
  });
  const assertionJSON = (c) => ({
    id: c.id,
    rawId: bufToB64u(c.rawId),
    type: c.type,
    authenticatorAttachment: c.authenticatorAttachment || undefined,
    clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
    response: {
      clientDataJSON: bufToB64u(c.response.clientDataJSON),
      authenticatorData: bufToB64u(c.response.authenticatorData),
      signature: bufToB64u(c.response.signature),
      userHandle: c.response.userHandle ? bufToB64u(c.response.userHandle) : null,
    },
  });
  const cancelled = (e) => e && (e.name === "NotAllowedError" || e.name === "AbortError");

  // ---- Settings: register this device
  async function initSettings() {
    const btn = $("#pkAddBtn");
    if (!btn) return;
    if (!(await supported())) {
      // No fingerprint / face sensor (or no WebAuthn): don't offer to register one.
      const note = $("#pkSupportNote"), n = $("#pkUnsupported");
      if (note) note.hidden = true;
      if (n) n.hidden = false;
      return;
    }
    const row = $("#pkAddRow");
    if (row) row.hidden = false;
    btn.hidden = false;
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      say("");
      try {
        const opt = await postJSON("/settings/passkeys/options");
        if (!opt.ok) return say(opt.data.detail || "Couldn't start. Try again.", true);
        const cred = await navigator.credentials.create({ publicKey: toCreate(opt.data.options) });
        const fin = await postJSON("/settings/passkeys/finish", { credential: attestationJSON(cred), name: ($("#pkName") || {}).value || "" });
        if (!fin.ok) return say(fin.data.detail || "That didn't work. Try again.", true);
        try { localStorage.setItem("dd-has-passkey", "1"); } catch (e) { /* storage blocked */ }
        say("Added. Reloading\u2026");
        location.href = "/settings?msg=Device+added#security";
      } catch (e) {
        say(cancelled(e) ? "Cancelled." : "Couldn't register this device.", true);
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ---- Login: second step
  async function initLogin() {
    const btn = $("#pkLoginBtn");
    if (!btn) return;
    if (!(await supported())) return;   // no sensor: the page is just the PIN form
    btn.hidden = false;
    document.querySelectorAll("[data-passkey-copy]").forEach((el) => (el.hidden = false));
    async function run() {
      btn.disabled = true;
      say("");
      try {
        const opt = await postJSON("/login/verify/webauthn/options");
        if (!opt.ok) return say(opt.data.detail || "Couldn't start. Use your PIN.", true);
        const cred = await navigator.credentials.get({ publicKey: toGet(opt.data.options) });
        const remember = !!($("#lv-remember") || {}).checked;
        const fin = await postJSON("/login/verify/webauthn/finish", { credential: assertionJSON(cred), remember });
        if (!fin.ok) return say(fin.data.detail || "Not recognised. Use your PIN.", true);
        location.href = fin.data.redirect || "/dashboard";
      } catch (e) {
        say(cancelled(e) ? "Cancelled. You can use your PIN below." : "Couldn't use the fingerprint or face. Use your PIN.", true);
      } finally {
        btn.disabled = false;
      }
    }
    btn.addEventListener("click", run);
    // Ask straight away only on a device that registered a passkey here; on a device that has a
    // sensor but never registered (e.g. the passkey is on the phone), show the button instead of
    // an OS prompt that can only fail. The PIN form is right below either way.
    let registeredHere = false;
    try { registeredHere = localStorage.getItem("dd-has-passkey") === "1"; } catch (e) { /* storage blocked */ }
    if (registeredHere) run();
  }

  // ---- Recovery: PIN or fingerprint/face, no email needed
  async function initRecovery() {
    const form = $("#pinRecoverForm");
    if (!form) return;
    const val = (n) => form.elements[n].value;
    const passwordsOk = () => {
      if (val("new_password").length < 8) { say("Choose a password of at least 8 characters.", true); return false; }
      if (val("new_password") !== val("confirm_password")) { say("The passwords don't match.", true); return false; }
      return true;
    };
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!val("username").trim() || !passwordsOk()) return;
      if (!/^\d{6,8}$/.test(val("pin").trim())) return say("Enter your 6 to 8 digit PIN.", true);
      const r = await postJSON("/forgot-password/pin-reset", { username: val("username"), pin: val("pin"), new_password: val("new_password") });
      if (r.ok) { say("Password changed. Taking you to sign in\u2026"); setTimeout(() => (location.href = "/login?msg=Password+changed"), 900); }
      else say(r.data.detail || "That didn't work.", true);
    });
    const btn = $("#pkRecoverBtn");
    if (btn && (await supported())) {
      btn.hidden = false;
      document.querySelectorAll("[data-passkey-copy]").forEach((el) => (el.hidden = false));
      btn.addEventListener("click", async () => {
        if (!val("username").trim() || !passwordsOk()) return;
        btn.disabled = true;
        say("");
        try {
          const opt = await postJSON("/forgot-password/webauthn/options", { username: val("username") });
          if (!opt.ok) return say(opt.data.detail || "Couldn't start.", true);
          const cred = await navigator.credentials.get({ publicKey: toGet(opt.data.options) });
          const fin = await postJSON("/forgot-password/webauthn/finish", { username: val("username"), credential: assertionJSON(cred) });
          if (!fin.ok) return say(fin.data.detail || "Not recognised for this account.", true);
          const done = await postJSON("/forgot-password/reset-with-grant", { grant: fin.data.grant, new_password: val("new_password") });
          if (!done.ok) return say(done.data.detail || "That didn't work.", true);
          say("Password changed. Taking you to sign in\u2026");
          setTimeout(() => (location.href = "/login?msg=Password+changed"), 900);
        } catch (e) {
          say(cancelled(e) ? "Cancelled." : "Couldn't use the fingerprint or face.", true);
        } finally {
          btn.disabled = false;
        }
      });
    }
  }

  function init() { initSettings(); initLogin(); initRecovery(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
