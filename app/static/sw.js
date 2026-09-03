// Service worker for Digital Diary's daily reminder push notifications.
// Deliberately minimal -- this app is server-rendered, not an offline-first
// SPA, so there's no asset caching here, just the two events Web Push
// actually needs a service worker for.

self.addEventListener("push", (event) => {
  let data = { title: "Digital Diary", body: "Time to write today's entry.", url: "/dashboard" };
  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/static/android-chrome-192x192.png",
      badge: "/static/favicon-32x32.png",
      data: { url: data.url || "/dashboard" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data && event.notification.data.url ? event.notification.data.url : "/dashboard";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      // If a tab for this app is already open, focus it and navigate
      // there instead of opening a duplicate tab.
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
