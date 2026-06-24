# Adding Status Dots on UI

Status dots are small colored circles on the dashboard that give at-a-glance feedback about hardware and process state. There are three different dot styles in [ui/templates/index.html](../../ui/templates/index.html), each updated by a different mechanism.

---

## The three existing dot types

### `status-dot` — cage acquisition process state

Element ID pattern: `dot-<cage_id>`

CSS classes: *(none)* = unreachable · `stopped` = process stopped · `alive` = receiving frames

Updated by `pollStatus()` which runs every 1 s. That function calls `GET /cameras/status` and sets the element's class:

```javascript
dot.className = 'status-dot' + (alive ? ' alive' : stopped ? ' stopped' : '');
```

### `periph-dot` — peripheral device state (fan, strip light)

Element ID pattern: `dot-<device>-<cage_id>` (e.g. `dot-fan-1`, `dot-strip-2`)

CSS class: `on` = active · *(none)* = inactive

Updated immediately after each successful command via `_setPeriphDot(id, device, on)`:

```javascript
function _setPeriphDot(id, device, on) {
    const dot = document.getElementById(`dot-${device}-${id}`);
    if (dot) dot.classList.toggle('on', on);
}
```

Also refreshed from the server in `pollPeripherals()` (every 1 s) for fan and strip state.

### `sync-dot` — NTP synchronisation status

Element ID pattern: `sync-dot-<cage_id>`

Updated by `pollSync()` (every 5 s) via `GET /cage/<id>/sync`. Turns green when the Pi's chrony offset is within the acceptable threshold.

---

## How to add a new status dot

### Step 1 — Add the HTML element

Find the cage card template string (around line 340 where `grid.innerHTML +=` appears) and add an element:

```html
<span class="periph-dot" id="dot-mydevice-${i}"></span>
```

Use `periph-dot` for binary on/off (same styling as fan/strip). Use `status-dot` if you need the three-state alive/stopped/unreachable look.

### Step 2 — Update the dot from a button action

If the dot reflects the result of a button press, call `_setPeriphDot()` in the success branch of your JS function:

```javascript
async function toggleMyDevice(id) {
    const next = !myDeviceActive[id];
    const res  = await post(`/cage/${id}/my-device`, { state: next });
    if (res.ok && res.data.ok) {
        myDeviceActive[id] = next;
        _setPeriphDot(id, 'mydevice', next);
    }
}
```

### Step 3 — Or update from a poll

If the dot reflects background state that can change without a user action, add your logic inside an existing poll function or create a new one and register it:

```javascript
async function pollMyDevice() {
    for (let i = 1; i <= N_CAGES; i++) {
        try {
            const res  = await fetch(`/cage/${i}/my-device/status`);
            const data = await res.json();
            _setPeriphDot(i, 'mydevice', data.active);
        } catch (_) {}
    }
}

// near the other setInterval calls (~line 1026):
setInterval(pollMyDevice, 2000);
```

Add the corresponding Flask endpoint that returns the current state as `{"active": true/false}` (see [09_endpoints.md](09_endpoints.md)).
