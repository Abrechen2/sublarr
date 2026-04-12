# Provider Transparency — Activity + Dashboard

**Created:** 2026-04-12
**Problem:** When providers are rate-limited or circuit-broken, the UI shows a frozen progress bar with no explanation. Users think the system is stuck.

## Goal

The user understands at all times why the search is slow or paused, without switching pages.

---

## Backend Changes

### 1. Extend `/api/v1/providers/health` response

Add 3 fields per provider:

```json
{
  "name": "animetosho",
  "healthy": false,
  "circuit_breaker_state": "open",
  "throttled_until": "2026-04-12T07:12:34Z",
  "throttle_reason": "rate_limited"
}
```

| Field | Type | Values | Source |
|-------|------|--------|--------|
| `circuit_breaker_state` | string | `closed`, `open`, `half_open` | `CircuitBreaker.state` property |
| `throttled_until` | string\|null | ISO timestamp or null | `RetryingSession._rate_limit_until` converted, or `disabled_until` from DB |
| `throttle_reason` | string\|null | `rate_limited`, `auto_disabled`, null | Derived from which source set the throttle |

**Implementation:** In `ProviderManager.get_provider_status()`, call `self._circuit_breakers[name].state` and check session rate-limit state. The circuit breaker already has `get_status()`. The session-level `_rate_limit_until` needs a public accessor.

### 2. New WebSocket event: `provider_state_changed`

Emitted when a provider transitions between states. This avoids polling — the frontend reacts immediately.

```json
{
  "provider": "animetosho",
  "state": "throttled",
  "reason": "rate_limited",
  "until": "2026-04-12T07:12:34Z",
  "remaining_seconds": 45
}
```

```json
{
  "provider": "animetosho",
  "state": "active",
  "reason": "cooldown_expired"
}
```

**Emit points:**
- `search_coordinator.py`: When `ProviderRateLimitError` is caught → emit `state: "throttled"`
- `search_coordinator.py`: When circuit breaker trips to OPEN → emit `state: "circuit_open"`
- `search_coordinator.py`: When auto-disable triggers → emit `state: "throttled", reason: "auto_disabled"`
- `providers/__init__.py`: When provider re-enabled → emit `state: "active"`

Register event in `events/catalog.py`.

### 3. Extend `wanted_search_progress` WebSocket payload

Add `provider_summary` field to existing progress events:

```json
{
  "processed": 39,
  "total": 10169,
  "found": 16,
  "failed": 0,
  "current_item": "Takamine-san — S01E05 [EN]",
  "provider_summary": {
    "active": 8,
    "throttled": 3,
    "circuit_open": 1,
    "throttled_providers": [
      { "name": "animetosho", "remaining_seconds": 42 },
      { "name": "jimaku", "remaining_seconds": 60 },
      { "name": "subdl", "remaining_seconds": 58 }
    ]
  }
}
```

**Implementation:** In `wanted_search_runner.py`, query provider manager state before each progress emit. Keep it lightweight — just count states and list throttled names with remaining seconds.

### 4. Expose rate-limit timestamp from session

Add public property to `RetryingSession`:

```python
@property
def rate_limit_remaining_seconds(self) -> float:
    if self._rate_limit_until and time.time() < self._rate_limit_until:
        return self._rate_limit_until - time.time()
    return 0.0
```

And in `ProviderManager`, add method to aggregate provider states:

```python
def get_provider_summary(self) -> dict:
    """Return counts of active/throttled/circuit-open providers."""
```

---

## Frontend Changes

### 5. Dashboard Provider-Status-Widget

**File:** `frontend/src/components/dashboard/DashboardSidebar.tsx` (ProviderHealthPanel)

**Current:** Shows top 5 providers with success rate % and green/red dot.

**New behavior:**
- Show status badge when provider is not in normal state
- Sort: problems first, then by success rate
- Countdown timer for throttled providers (local `setInterval`, decrements from `remaining_seconds`)

**Visual states per provider:**

| State | Indicator | Text | Color |
|-------|-----------|------|-------|
| Healthy | `●` | `26%` | green (var(--success)) |
| Throttled | `◆` | `Throttled 42s` | orange (var(--warning)) |
| Circuit Open | `◆` | `Circuit Open` | orange (var(--warning)) |
| Auth Error | `✕` | `Auth Error` | red (var(--error)) |
| Auto-disabled | `✕` | `Disabled` | red (var(--error)) |

**Data source:** Existing `useProviderHealth()` hook (30s poll) + new `provider_state_changed` WebSocket event for immediate updates.

**Countdown logic:** When a provider has `throttled_until`, compute `remaining_seconds` locally. Start a `setInterval(1000)` that decrements. When it hits 0, remove the badge. No server round-trip needed for the tick.

### 6. Activity Queue — Provider Status Line

**File:** `frontend/src/components/activity/` (Queue tab rendering)

**New element:** A single line below the current search progress bar, only visible during active Wanted search.

**States:**

All providers active:
```
⚡ 8 Provider aktiv
```

Some throttled:
```
⏳ 5 aktiv · 3 gedrosselt (animetosho 42s, jimaku 60s, subdl 58s)
```

Most throttled (>50% of enabled providers):
```
⚠️ 2 aktiv · 9 gedrosselt — Suche verlangsamt
```

**Data source:** `provider_summary` field from `wanted_search_progress` WebSocket event. Countdown timers tick locally.

**i18n keys:** Add to `de/activity.json` and `en/activity.json`:
- `search.providers_active`: `{{count}} Provider aktiv` / `{{count}} providers active`
- `search.providers_throttled`: `{{active}} aktiv · {{throttled}} gedrosselt` / `{{active}} active · {{throttled}} throttled`
- `search.providers_mostly_throttled`: `{{active}} aktiv · {{throttled}} gedrosselt — Suche verlangsamt` / `{{active}} active · {{throttled}} throttled — search slowed`

### 7. WebSocket event listener

**File:** `frontend/src/hooks/useWebSocket.ts`

Register listener for `provider_state_changed`. On receipt, invalidate the `providerHealth` React Query cache so the dashboard widget updates immediately without waiting for the 30s poll.

---

## What we intentionally skip

- No dedicated Provider Health panel/page — dashboard widget is sufficient
- No notifications on rate limits — would be spam during normal operation
- No rate-limit history — not useful for users
- No manual "clear throttle" button — providers recover automatically
- No per-search provider breakdown — too granular, adds noise

---

## Files to modify

| File | Change |
|------|--------|
| `backend/circuit_breaker.py` | No changes needed (state already queryable) |
| `backend/providers/http_session.py` | Add `rate_limit_remaining_seconds` property |
| `backend/providers/__init__.py` | Add `get_provider_summary()`, extend `get_provider_status()` with CB + throttle fields |
| `backend/providers/search_coordinator.py` | Emit `provider_state_changed` events on rate-limit/CB transitions |
| `backend/services/wanted_search_runner.py` | Add `provider_summary` to progress WebSocket payload |
| `backend/events/catalog.py` | Register `provider_state_changed` event |
| `backend/routes/providers.py` | Extend `/health` response with new fields |
| `frontend/src/hooks/useWebSocket.ts` | Add `provider_state_changed` listener |
| `frontend/src/hooks/useProvidersApi.ts` | Extend health response type |
| `frontend/src/components/dashboard/DashboardSidebar.tsx` | Status badges, countdown, sort order |
| `frontend/src/components/activity/QueueTab.tsx` (or equivalent) | Provider status line |
| `frontend/src/i18n/locales/de/activity.json` | New keys |
| `frontend/src/i18n/locales/en/activity.json` | New keys |
