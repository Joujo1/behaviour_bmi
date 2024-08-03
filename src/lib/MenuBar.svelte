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
        break;
      case "monitor-btn":
        $store.showMonitor = !$store.showMonitor;
        break;
      case "analyze-btn":
        $store.showAnalyze = !$store.showAnalyze;
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
  $: analyzeBtnCol = $store.showAnalyze
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
<li>
  <a
    id="setup-btn"
    href="#"
    on:click={switchMenuItem}
    style="color: {setupBtnCol};">Setup</a
  >
</li>
<li>
  <a
    id="monitor-btn"
    href="#"
    on:click={switchMenuItem}
    style="color: {monitorBtnCol};">Monitor</a
  >
</li>
<li>
  <a
    id="analyze-btn"
    href="#"
    on:click={switchMenuItem}
    style="color: {analyzeBtnCol};">Analyze</a
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
