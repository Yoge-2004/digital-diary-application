# Setting up "Continue with Google"

The app supports Google OAuth sign-in/sign-up, but it's off by default —
until you configure real credentials, the "Continue with Google" button
simply doesn't render on the login/register pages, and the OAuth routes
redirect back to `/login` with a clear error instead of doing anything.

## 1. Create a Google OAuth client

1. Go to https://console.cloud.google.com/apis/credentials (create a
   project first if you don't have one).
2. **Create Credentials → OAuth client ID**.
3. Application type: **Web application**.
4. Under **Authorized redirect URIs**, add:
   - `http://127.0.0.1:8000/auth/google/callback` for local development
   - `https://yourdomain.com/auth/google/callback` for production

   This must match exactly (scheme, host, path) — Google will reject the
   callback otherwise. If you run the app on a different host/port
   locally, use that instead of `127.0.0.1:8000`.
5. You'll also likely need to configure the **OAuth consent screen**
   (app name, support email) before Google lets you create the client
   if this is a new project.
6. Save. Google gives you a **Client ID** and **Client Secret**.

## 2. Set environment variables

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
```

Both must be set — if either is missing, the feature stays disabled.

## 3. Restart the app

That's it. The "Continue with Google" button now appears on `/login`
and `/register`.

## How it behaves

- **New Google sign-in, no existing account** → creates a new account
  automatically (username derived from the email/display name, made
  unique if it collides with an existing one).
- **Google sign-in with an email that already has a password account**
  → links the Google identity to that existing account rather than
  creating a duplicate. The original password keeps working too.
- **Signing in with the same Google account again** → finds and reuses
  the same account; never creates a duplicate.
- Accounts created via Google still get a `password_hash` in the
  database (a long random value nobody can know), because this app has
  no migration tooling to safely make that column nullable on an
  existing database. It just means password login can never succeed
  for a Google-only account — only the Google button can sign it in,
  unless the person also sets a password later.

## Testing without a real Google account

`tests/test_oauth.py` covers the whole flow (new user, duplicate-login
idempotency, account linking, bad state, user cancellation) using
`respx` to mock Google's token/userinfo endpoints — no real network
calls or real Google credentials needed to run the test suite.
