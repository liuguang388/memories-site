// ══════════════════════════════════════════════════════════════
//  记忆时光 - Service Worker
//  缓存策略：关键静态资源预缓存，API 数据网络优先
// ══════════════════════════════════════════════════════════════

const CACHE_VERSION = 'v2';
const CACHE_NAME = 'memories-' + CACHE_VERSION;

// 预缓存的静态资源
const PRECACHE_URLS = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/js/particles.js',
  '/static/manifest.json',
  '/offline'
];

// ─── Install: 预缓存关键资源 ──────────────────────────────────
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(PRECACHE_URLS).catch(function(err) {
        console.warn('SW: precache partial failure', err);
      });
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

// ─── Activate: 清理旧缓存 ─────────────────────────────────────
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; })
            .map(function(k) { return caches.delete(k); })
      );
    }).then(function() {
      return self.clients.claim();
    })
  );
});

// ─── Fetch: 策略分发 ──────────────────────────────────────────
self.addEventListener('fetch', function(event) {
  var url = new URL(event.request.url);

  // 跳过非 GET 请求和浏览器扩展
  if (event.request.method !== 'GET') return;

  // Cloudinary / supabase 图片：网络优先，失败用缓存
  if (url.hostname.includes('cloudinary.com') ||
      url.hostname.includes('supabase.co')) {
    event.respondWith(networkFirstWithCache(event.request));
    return;
  }

  // API 请求：仅网络（不缓存动态数据）
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkOnly(event.request));
    return;
  }

  // HTML / 静态资源：缓存优先，网络更新
  event.respondWith(staleWhileRevalidate(event.request));
});

// ─── 策略函数 ─────────────────────────────────────────────────

function networkFirstWithCache(request) {
  return fetch(request).then(function(response) {
    if (response.ok) {
      var cloned = response.clone();
      caches.open(CACHE_NAME).then(function(cache) {
        cache.put(request, cloned);
      });
    }
    return response;
  }).catch(function() {
    return caches.match(request);
  });
}

function networkOnly(request) {
  return fetch(request).catch(function() {
    return new Response(JSON.stringify({ error: 'offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  });
}

function staleWhileRevalidate(request) {
  return caches.open(CACHE_NAME).then(function(cache) {
    return cache.match(request).then(function(cached) {
      var fetchPromise = fetch(request).then(function(networkResponse) {
        if (networkResponse.ok) {
          cache.put(request, networkResponse.clone());
        }
        return networkResponse;
      });
      return cached || fetchPromise;
    });
  });
}
