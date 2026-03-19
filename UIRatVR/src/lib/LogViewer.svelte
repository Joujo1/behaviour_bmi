<script>
  import { store } from "../../store/stores";
  import { openWebsocket } from "../monitor_api";
  import { AnsiUp } from 'ansi_up';

  let initiatedState = false;
  let proccessSessionProcState = 0;
  let closeCallback = () => {};
  let activeTab = null;
  let logs = {};

  const ansi_up = new AnsiUp();

  function onMessageCallback(message) {
    const data = JSON.parse(message.data);
    // console.log(Object.keys(data));
    logs = data;
    
    // should only send updates in the future 
    // logs += data;

    for (const [key, value] of Object.entries(data)) {
    // count the number of "WARNING" and "ERROR" in the log
    const warningCount = (value.match(/WARNING/g) || []).length;
    const errorCount = (value.match(/ERROR/g) || []).length;
    // console.log(key, warningCount, errorCount);
    switch (key) {
      case "portenta2shm2portenta.log":
        $store.por2shm2por_warnings = warningCount;
        $store.por2shm2por_errors = errorCount;
        break;
      case "facecam2shm.log":
        $store.facecam2shm_warnings = warningCount;
        $store.facecam2shm_errors = errorCount;
        break;
      case "ttlcam22shm.log":
        $store.ttl2cam2shm_warnings = warningCount;
        $store.ttl2cam2shm_errors = errorCount;
        break;
      case "ttlcam32shm.log":
        $store.ttl3cam2shm_warnings = warningCount;
        $store.ttl3cam2shm_errors = errorCount;
        break;
      case "ttlcam42shm.log":
        $store.ttl4cam2shm_warnings = warningCount;
        $store.ttl4cam2shm_errors = errorCount;
        break;
      case "bodycam2shm.log":
        $store.bodycam2shm_warnings = warningCount;
        $store.bodycam2shm_errors = errorCount;
        break;
      case "unity.log":
        $store.unity_warnings = warningCount;
        $store.unity_errors = errorCount;
        break;
      case "log_portenta.log":
        $store.log_portenta_warnings = warningCount;
        $store.log_portenta_errors = errorCount;
        break;
      case "log_facecam.log":
        $store.log_facecam_warnings = warningCount;
        $store.log_facecam_errors = errorCount;
        break;
      case "log_ttlcam2.log":
        $store.log_ttl2cam_warnings = warningCount;
        $store.log_ttl2cam_errors = errorCount;
        break
      case "log_ttlcam3.log":
        $store.log_ttl3cam_warnings = warningCount;
        $store.log_ttl3cam_errors = errorCount;
        break
      case "log_ttlcam4.log":
        $store.log_ttl4cam_warnings = warningCount;
        $store.log_ttl4cam_errors = errorCount;
        break
      case "log_bodycam.log":
        $store.log_bodycam_warnings = warningCount;
        $store.log_bodycam_errors = errorCount;
        break;
      case "log_unity.log":
        $store.log_unity_warnings = warningCount;
        $store.log_unity_errors = errorCount;
        break;
      case "log_unitycam.log":
        $store.log_unitycam_warnings = warningCount;
        $store.log_unitycam_errors = errorCount;
        break;
      case "process_session.log":
        $store.process_session_warnings = warningCount;
        $store.process_session_errors = errorCount;
        break;
      case "por2shm2por_sim.log":
        $store.por2shm2por_sim_warnings = warningCount;
        $store.por2shm2por_sim_errors = errorCount;
        break;
      }
    }
  }

  function switchTab(tab) {
    activeTab = tab;
  }

  $: if ($store.initiated != initiatedState) {
    if ($store.initiated) {
      initiatedState = true;
      console.log("LogViewer initiated");
      closeCallback = openWebsocket('logfiles', onMessageCallback);
    } else {
      initiatedState = false;

      if ($store.process_session == 0) {
        console.log("LogViewer closed");
        closeCallback();
      }
    }
  }

  // when process_session termiantes close the websocket
  $: if ($store.process_session != proccessSessionProcState) {
    if ($store.process_session == 0) {
      console.log("Process session terminated, closing logfiles websocket");
      setTimeout(() => {
        closeCallback();
      }, 2000);
    } else {

    }
    console.log("Process session state changed");
    console.log($store.process_session);
    proccessSessionProcState = $store.process_session;
  }


  function close() {
    $store.showLogfiles = false;
  }

  function resetLogViewer() {
    logs = {};
    closeCallback();
    $store.por2shm2por_warnings = 0;
    $store.por2shm2por_errors = 0;
    $store.facecam2shm_warnings = 0;
    $store.facecam2shm_errors = 0;
    $store.bodycam2shm_warnings = 0;
    $store.bodycam2shm_errors = 0;
    $store.unity_warnings = 0;
    $store.unity_errors = 0;
    $store.log_portenta_warnings = 0;
    $store.log_portenta_errors = 0;
    $store.log_facecam_warnings = 0;
    $store.log_facecam_errors = 0;
    $store.log_bodycam_warnings = 0;
    $store.log_bodycam_errors = 0;
    $store.log_unity_warnings = 0;
    $store.log_unity_errors = 0;
    $store.log_unitycam_warnings = 0;
    $store.log_unitycam_errors = 0;
    $store.process_session_warnings = 0;
    $store.process_session_errors = 0;
    $store.por2shm2por_sim_warnings = 0;
    $store.por2shm2por_sim_errors = 0;

    if ($store.initiated ) {
      closeCallback = openWebsocket('logfiles', onMessageCallback);
    }
  }
</script>

{#if $store.showLogfiles}
  <div class="modal">
    <div class="modal-content">
      <div id="button-div">

        <button
        title="Reset the log viewer"
        class="close-button"
        on:click={resetLogViewer}
        aria-label="Refresh"
      >
      <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      class="feather feather-refresh-cw"
    >
      <g transform="translate(4, 0)">
        <line x1="6" y1="19" x2="6" y2="5"></line>
        <!-- <polyline points="3 13 6 10 9 13"></polyline> -->
        <polyline points="3 10 6 7 9 10"></polyline>
      </g>
      <g transform="translate(12, 0)">
        <line x1="6" y1="5" x2="6" y2="20"></line>
        <polyline points="3 14 6 17 9 14"></polyline>
      </g>
    </svg>
      </button>
      <button
        class="close-button"
        on:click={close}
        aria-label="Close"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="feather feather-x"
        >
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div>

      <div class="tabs">
        {#each Object.keys(logs) as tab}
          <button on:click={() => switchTab(tab)} class:active={activeTab === tab}>{tab}</button>
        {/each}
      </div>
      <div class="log-content">
        <pre>{@html ansi_up.ansi_to_html(logs[activeTab])}</pre>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal {
    position: fixed;
    z-index: 1;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    overflow: auto;
    background-color: var(--bg-color);
  }

  .modal-content {
    background-color: var(--bgFaint-color);
    margin: 5% auto;
    padding: 20px;
    width: 50%; /* Reduced width */
    border-radius: 10px;
    font-size: larger;
    display: flex;
    flex-direction: column;
    height: 90%; /* Ensure it fills most of the screen height */
  }

  #button-div {
    display: flex;
    justify-content: flex-end;
  }

  .close-button {
    color: var(--fg-color);
    align-self: flex-end;
    font-size: 28px;
    font-weight: bold;
    border: none;
  }

  .close-button:hover,
  .close-button:focus {
    color: var(--fg-color);
    text-decoration: none;
    cursor: pointer;
  }

  .tabs {
    display: flex;
    flex-wrap: wrap;
    margin-bottom: 20px;
  }
  
  .tabs button {
    margin-right: 2em;
    background-color: var(--faintbg-color);
    padding: 10px 20px;
    border: 2px solid var(--bgFaint-color);
    border-radius: 5px;
    cursor: pointer;
    font-size: 16px;
    color: var(--fg-color);
  }

  .tabs button:hover {
    border: 2px solid var(--fgFaint-color);
  }

  .tabs button.active {
    border-bottom: 4px solid var(--accent-color);
  }

  .log-content {
    background-color: var(--bg-color);
    padding: 10px;
    border-radius: 5px;
    flex-grow: 1; /* Ensure it takes up remaining space */
    overflow-y: auto;
    font-family: monospace;
  }

  pre {
    margin: 0;
  }
</style>