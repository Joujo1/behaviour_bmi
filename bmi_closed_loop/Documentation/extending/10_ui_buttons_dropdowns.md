# Adding UI Buttons and Dropdowns

The UI has two main templates: [ui/templates/index.html](../../ui/templates/index.html) is the dashboard, and [ui/templates/curriculum.html](../../ui/templates/curriculum.html) contains the trial builder and curriculum editor. Both templates use plain JavaScript — no build step, no framework.

---

## Dashboard buttons (index.html)

### How a button works

Each per-cage button in `index.html` is created inside a JavaScript template string that generates the cage cards at startup. The button's `onclick` calls a JavaScript function, which uses `fetch` to call a REST endpoint, then updates the UI based on the response.

A minimal example — the strip light toggle button:

```html
<button class="btn small" onclick="toggleStrip(${i})">💡</button>
```

```javascript
async function toggleStrip(id) {
    const next = !stripActive[id];
    const res  = await post(`/cage/${id}/strip`, { state: next });
    if (res.ok && res.data.ok) {
        stripActive[id] = next;
        _setPeriphDot(id, 'strip', next);
    } else {
        toast(`Cage ${id} strip: ${res.data?.msg || 'failed'}`);
    }
}
```

`post()` is a thin helper defined near the top of the `<script>` block that wraps `fetch` with `method: 'POST'` and `Content-Type: application/json`, then returns `{ok, data}`.

### Adding a per-cage button

1. Find the cage card template string (starts around line 340 where `grid.innerHTML +=` appears) and add your button in the appropriate row.
2. Write a JavaScript function that calls `post()` or `fetch()` with the correct endpoint URL.
3. Add the corresponding Flask endpoint (see [09_endpoints.md](09_endpoints.md)).

### Adding a global ("all cages") button

Global buttons live in the dev/control panel section around lines 300–310. They iterate over all cage IDs and call the per-cage function for each:

```javascript
async function startAllMyFeature() {
    for (let i = 1; i <= N_CAGES; i++) await myFeature(i);
}
```

Then add the button in the HTML:

```html
<button class="btn small" onclick="startAllMyFeature()">Start All My Feature</button>
```

---

## Curriculum builder dropdowns (curriculum.html)

### Action type dropdown

The trial builder renders a `<select>` for each action entry. The available options come from a single array at line 417:

```javascript
const ACTION_TYPES = ['led_on','led_off','valve_open','play_clicks'];
```

To add a new action type, append its key to this array:

```javascript
const ACTION_TYPES = ['led_on','led_off','valve_open','play_clicks','puff_air'];
```

The key must match the `"type"` value used in the trial JSON and the key registered in `ACTIONS` in [RPi_main/actions.py](../../RPi_main/actions.py) (see [05_actions.md](05_actions.md)).

### Action-specific parameter fields

After selecting an action type, `renderStateCard()` (around line 837) shows extra input fields for that type's parameters. If your new action needs parameters beyond a `target` dropdown, add a branch to the `extraFields` block:

```javascript
const extraFields = a.type === 'play_clicks'
    ? `...click fields...`
    : a.type === 'valve_open'
    ? `...valve fields...`
    : a.type === 'puff_air'
    ? `<input ... oninput="bldrStates[${idx}]['${phase}'][${ai}]['duration_ms']=+this.value">`
    : `<input class="bldr-input" placeholder="target" ...>`;
```

This block appears twice in the file (once for entry actions, once for exit actions in `renderTerminalCards()`).

### Criteria type dropdown

The criteria type dropdown is populated dynamically — it fetches `GET /criteria-types` from the server, which reads `CRITERIA_HANDLERS` in `advancement.py` directly. No change is needed in the template when you add a new criterion type.

However, the criteria parameter fields (`window`, `threshold`) are hardcoded. If your new criterion uses different parameter names, update the criteria form in `curriculum.html` to add or rename the corresponding input fields.

---

## Conventions

- All buttons use the CSS class `btn small` for styling.
- Status indicators use `periph-dot` elements updated via `_setPeriphDot(id, device, on)`.
- Toast notifications for non-fatal errors use `toast(message)`.
- All `fetch` calls go through the `post()` helper or plain `fetch()` with `await`. Never call an endpoint synchronously.
