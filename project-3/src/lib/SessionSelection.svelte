<script>
  import { store } from "../../store/stores";
  import {
    GETSessions,
    POSTSessionSelection,
    GETCurrentSession,
    POSTTerminateInspection,
  } from "../inspect_api.js";

  import MonitorDropdown from "./MonitorDropdown.svelte";
  import SetupUiButton from "./SetupUIButton.svelte";
  import FlipSwitch from "./FlipSwitch.svelte";

  function handlePOSTResult(result) {
    console.log(result);
    if (result !== true) {
      $store.showModal = true;
      $store.modalMessage = result.detail;
    }
  }

  let sessions = [];
  let paradigms = [];
  let animals = [];

  let sessionSelection;
  let paradigmSelection;
  let animalSelection;
  let useNAS = true;

  async function getSessions() {
    sessions = await GETSessions();
    console.log(sessions);
  }

  function getParadigms() {
    const paradigmsSet = new Set();
    sessions.forEach((session) => {
      paradigmsSet.add(session.paradigm);
    });
    paradigms = Array.from(paradigmsSet).sort((a, b) => a.localeCompare(b));
  }

  function getAnimals() {
    const animalsSet = new Set();
    sessions.forEach((session) => {
      animalsSet.add(session.animal);
    });
    animals = Array.from(animalsSet).sort((a, b) => a.localeCompare(b));
  }

  async function loadSession() {
    if (!sessionSelection) {
      $store.modalMessage = "Please select a session";
      $store.showModal = true;
      return;
    }

    console.log("Loading session", sessionSelection);
    let result = await POSTSessionSelection(sessionSelection);
    console.log(result);
    handlePOSTResult(result);
  }

  async function resetSelection() {
    let result = await POSTTerminateInspection();
    handlePOSTResult(result);
    console.log("Resetting session selection");
  }

  async function getOptions() {
    await getSessions();
    getParadigms();
    getAnimals();

    if ($store.initiatedInspect) {
      const currentSession = (await GETCurrentSession()) + ".hdf5";
      console.log("Current session", currentSession);
      sessionSelection = currentSession;
    }
  }

  $: if ($store.showInspect && sessions.length === 0) {
    getOptions();
  }
</script>

<div id="session-selection-div">
  <div>
    <MonitorDropdown
      label="Animal"
      bind:value={animalSelection}
      isEnabled={!$store.initiatedInspect && sessions.length > 0}
      options={animals}
      getOptions={getAnimals}
      width={210}
    />
    <MonitorDropdown
      label="Paradigm"
      bind:value={paradigmSelection}
      isEnabled={!$store.initiatedInspect && sessions.length > 0}
      options={paradigms}
      getOptions={getParadigms}
      width={215}
    />
    <MonitorDropdown
      label="Session"
      bind:value={sessionSelection}
      isEnabled={!$store.initiatedInspect && sessions.length > 0}
      options={sessions
        .filter(
          (session) =>
            (!animalSelection || session.animal === animalSelection) &&
            (!paradigmSelection || session.paradigm === paradigmSelection)
        )
        .sort((a, b) => a.session.localeCompare(b.session)) // Sorting the sessions
        .map((session) => session.session)}
      width={205}
    />
    <div id="session-selection-buttons-div">
      <FlipSwitch {useNAS} isEnabled={!$store.initiated} />
      <SetupUiButton
        label="Load Session"
        onClickCallback={loadSession}
        stateDependancy={$store.initiatedInspect}
        background_color="var(--bgFaint-color)"
      />
      <button
        class="close-button"
        on:click={resetSelection}
        aria-label="Close"
        title="Reset the session selection"
        style="width: 27px; height: 27px; border: none; padding: 0; margin-top: 10px;"
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
  </div>
</div>

<style>
  #session-selection-div {
    width: 350px;
  }

  #session-selection-buttons-div {
    margin-top: 20px;
    /* margin-bottom: 20px; */
    display: flex;
    justify-content: space-between;
  }
  .close-button {
    /* color: var(--fg-color); */
    float: right;
    /* font-size: 28px; */
    /* font-weight: bold; */
    border: none;
    background-color: var(--bg-color);
  }

  .close-button:hover,
  .close-button:focus {
    color: var(--fg-color);
    background-color: var(--fgFaint-color);
    text-decoration: none;
    cursor: pointer;
  }
</style>
