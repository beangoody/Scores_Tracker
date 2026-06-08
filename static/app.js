// app.js — Trackr client-side JS

// ── Register service worker + set up push notifications ──────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/static/sw.js');
      console.log('Trackr SW registered:', reg.scope);

      // Only ask for push permission if the user is logged in
      // (check for the bottom nav as a proxy — it only renders when authed)
      const isLoggedIn = !!document.querySelector('.bottomnav');
      if (isLoggedIn) {
        await setupPushNotifications(reg);
      }
    } catch (err) {
      console.warn('Trackr SW failed:', err);
    }
  });
}

async function setupPushNotifications(registration) {
  // Don't ask again if already granted or denied
  if (Notification.permission === 'denied') return;

  // Get our VAPID public key from the server
  let publicKey;
  try {
    const res = await fetch('/push/vapid-public');
    const data = await res.json();
    publicKey = data.publicKey;
    if (!publicKey) return;  // VAPID not configured yet
  } catch (e) {
    return;
  }

  // Check if already subscribed
  let subscription = await registration.pushManager.getSubscription();

  if (!subscription) {
    // Not subscribed yet — request permission and subscribe
    // We wait a moment so we don't immediately pop up on first load
    setTimeout(async () => {
      try {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') return;

        subscription = await registration.pushManager.subscribe({
          userVisibleOnly:      true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        });

        // Save subscription to server
        await fetch('/push/subscribe', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify(subscription.toJSON()),
        });

        console.log('Trackr: push notifications enabled');
      } catch (err) {
        console.warn('Trackr: push subscription failed:', err);
      }
    }, 3000);  // 3 second delay — don't ask immediately on page load
  } else {
    // Already subscribed — re-register with server in case it expired
    await fetch('/push/subscribe', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(subscription.toJSON()),
    });
  }
}

// ── Helper: convert VAPID key ─────────────────────────────────────────────────
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64  = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw     = window.atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

// ── Flash message auto-dismiss ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash').forEach(flash => {
    setTimeout(() => {
      flash.style.transition = 'opacity 0.5s';
      flash.style.opacity    = '0';
      setTimeout(() => flash.remove(), 500);
    }, 4000);
  });
});