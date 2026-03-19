<script>
  import { store } from "../../store/stores";

  function switchMenuItem(event) {
    // console.log("menuclick", event.target.id);
    switch (event.target.id) {
      case "parameters-btn":
        $store.showParameters = !$store.showParameters;
        break;
      case "setup-btn":
        $store.showSetup = !$store.showSetup;
        if ($store.showInspect) $store.showInspect = false;
        break;
      case "analyze-btn":
        $store.showInspect = !$store.showInspect;
        if ($store.showSetup) $store.showSetup = false;
        break;
      case "monitor-btn":
        $store.showMonitor = !$store.showMonitor;
        break;
    }
  }

  $: parametersBtnCol = $store.showParameters
    ? "var(--fg-color)"
    : "var(--fgFaint-color)";
  $: setupBtnCol = $store.showSetup
    ? "var(--fg-color)"
    : "var(--fgFaint-color)";
  $: monitorBtnCol = $store.showMonitor
    ? "var(--fg-color)"
    : "var(--fgFaint-color)";
  $: analyzeBtnCol = $store.showInspect
    ? "var(--fg-color)"
    : "var(--fgFaint-color)";
</script>

<li>
  <a
    id="parameters-btn"
    href="#"
    on:click={switchMenuItem}
    style="color: {parametersBtnCol};">Parameters</a
  >
</li>
  <!-- not references as acquire, but 'monitor' everywh≈ere  -->
<li>
  <a
    id="setup-btn"
    href="#"
    on:click={switchMenuItem}
    style="color: {setupBtnCol};">Acquire</a
  >
</li>
<li>
  <a
    id="analyze-btn"
    href="#"
    on:click={switchMenuItem}
    style="color: {analyzeBtnCol};">Inspect</a
  >
</li>
  <!-- not references as Session, but 'setup' everywh≈ere  -->
<li>
  <a
    id="monitor-btn"
    href="#"
    on:click={switchMenuItem}
    style="color: {monitorBtnCol};">Session</a
  > 
</li>

<style>
  #parameters-btn,
  #setup-btn,
  #monitor-btn,
  #analyze-btn {
    text-decoration: none;
    /* color: var(--fgFaint-color); */
    font-size: 14pt;
    font-weight: bold;
    transition: color 0.1s ease;
  }
  #parameters-btn:hover,
  #setup-btn:hover,
  #monitor-btn:hover,
  #analyze-btn:hover {
    background: rgba(124, 124, 124, 0.15);
  }
</style>
