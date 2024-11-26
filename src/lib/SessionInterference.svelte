<script>
  import { store } from "../../store/stores";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import SetupUIInput from "./SetupUIInput.svelte";
  import MonitorDropdown from "./MonitorDropdown.svelte";
  import MonitorInputField from "./MonitorInputField.svelte";
  import { POSTUnityInput } from "../monitor_api.js";
  import { GETTrialVarialbeNames } from "../monitor_api.js";
  import { GETTrialVarialbeDefaultValues } from "../monitor_api.js";
  import { GETAnimals } from "../monitor_api.js";
  import { POSTAnimal } from "../monitor_api.js";
  import { POSTAnimalWeight } from "../monitor_api.js";
  import { onMount } from "svelte";
  import Setup from "./Setup.svelte";

  let successLengthTextValue = 20;
  let successDelayTextValue = 0;
  let punishmentLengthTextValue = 100;
  let vacuumLengthTextValue = 12;
  let teleportXTextValue = 0;
  let teleportZTextValue = 0;
  let teleportAngleTextValue = 0;
  let distanceDelta = 1;
  let angleDelta = 5;

  let paradigmVariableValues = [];
  let paradigmVariables = [];
  let paradigmVariablesFullNames = {};
  let paradigmVariableSelection;

  function handlePOSTResult(result) {
    console.log(result);
    if (result !== true) {
      $store.showModal = true;
      $store.modalMessage = result;
    }
  }

  async function stopSession() {
    const unityMsg = "Stop";
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendAirvalve() {
    const unityMsg = "Airvalve";
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendSucess() {
    const unityMsg = `Success,${successLengthTextValue},${successDelayTextValue}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendFailure() {
    const unityMsg = "Failure";
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendPunishment() {
    const unityMsg = `Punishment,${punishmentLengthTextValue}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendVacuum() {
    const unityMsg = `Vacuum,${vacuumLengthTextValue}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendTeleport() {
    const unityMsg = `Teleport,${teleportXTextValue},${teleportZTextValue},${teleportAngleTextValue}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendMute() {
    const unityMsg = "Mute";
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  // async function sendDistanceDelta() {
  //   const unityMsg = `TrialEndTeleportDistanceDelta,${distanceDelta}`;
  //   const result = await POSTUnityInput(unityMsg);
  //   handlePOSTResult(result);
  // }
  // async function sendAngleDelta() {
  //   const unityMsg = `TrialEndTeleportAngleDelta,${angleDelta}`;
  //   const result = await POSTUnityInput(unityMsg);
  //   handlePOSTResult(result);
  // }

  // Function to send updated paradigm variables
  async function sendUpdatedParadigmVariables() {
    // Construct an object from the keys and values
    const variablesObject = paradigmVariables.reduce((obj, key, index) => {
      if (key === "C") {
        console.log("C (cue) won't be updated");
        return obj;
      }
      obj[key] = paradigmVariableValues[index];
      return obj;
    }, {});
    // Convert the object into a string format for Unity
    const value = JSON.stringify(variablesObject);

    const unityMsg = `TrialVariables,${value}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }

  async function getParadigmVarialbeNames() {
    paradigmVariablesFullNames = await GETTrialVarialbeNames();
    paradigmVariables = Object.keys(paradigmVariablesFullNames);
    console.log("GET:", paradigmVariables);
    console.log("GET:", paradigmVariablesFullNames);
  }

  async function getParadigmVarialbeDefaultValues() {
    paradigmVariableValues = await GETTrialVarialbeDefaultValues();
  }

  let previousparadigmRunning = $store.paradigmRunning;

  $: if ($store.paradigmRunning !== previousparadigmRunning) {
    console.log("ParadigmVariable UI updating...");
    if ($store.paradigmRunning) {
      (async () => {
        console.log("Waiting for 4s...");
        await new Promise((r) => setTimeout(r, 1000));
        console.log("Done waiting...");

        getParadigmVarialbeNames();
        getParadigmVarialbeDefaultValues();
      })();
    } else {
      paradigmVariables = [];
      paradigmVariableValues = [];
    }
    console.log(paradigmVariableValues);
    console.log(paradigmVariables);

    // Update the previous value to the current one for the next check
    previousparadigmRunning = $store.paradigmRunning;
  }
</script>

<!-- <div id="setup-div" class={$store.showMonitor ? "" : "hide"}> -->
<SetupUIBlock>
  <div slot="header">Session Interference</div>
  <div slot="setupui">
    <div class="button-row-div">
      <SetupUIButton label="Success" onClickCallback={sendSucess} />
      <SetupUIInput
        bind:value={successLengthTextValue}
        tooltip="opened-for [ms]"
      ></SetupUIInput>
      <SetupUIInput bind:value={successDelayTextValue} tooltip="delay [ms]"
      ></SetupUIInput>
      <div style="margin-left: 160px;">
        <SetupUIButton label="Failure" onClickCallback={sendFailure} />
      </div>
    </div>

    <div class="button-row-div">
      <SetupUIButton label="Airpuff" onClickCallback={sendPunishment} />
      <SetupUIInput
        bind:value={punishmentLengthTextValue}
        tooltip="airvalve opening time [ms]"
      ></SetupUIInput>

      <div style="margin-left: 155px;">
        <SetupUIButton label="Vacuum" onClickCallback={sendVacuum} />
      </div>

      <SetupUIInput
        bind:value={vacuumLengthTextValue}
        tooltip="suction time [ms]"
      ></SetupUIInput>
    </div>

    <div class="button-row-div">
      <SetupUIButton label="Teleport" onClickCallback={sendTeleport} />
      <SetupUIInput bind:value={teleportXTextValue} tooltip="X position"
      ></SetupUIInput>
      <SetupUIInput bind:value={teleportZTextValue} tooltip="Z position"
      ></SetupUIInput>
      <SetupUIInput bind:value={teleportAngleTextValue} tooltip="Angle"
      ></SetupUIInput>
      <div style="margin-left: 106px;">
        <SetupUIButton label="Mute" onClickCallback={sendMute} />
      </div>
    </div>

    <div class="button-row-div">
      <MonitorDropdown
        label="Trial Variable"
        bind:value={paradigmVariableSelection}
        options={paradigmVariables}
        getOptions={getParadigmVarialbeNames}
        title={paradigmVariablesFullNames[paradigmVariableSelection]}
      />
      <SetupUIInput
        bind:value={paradigmVariableValues[
          paradigmVariables.indexOf(paradigmVariableSelection)
        ]}
        tooltip="The updated value of the trial variable"
      ></SetupUIInput>
      <div style="margin-left: 40px;">
        <SetupUIButton
          label="Update"
          onClickCallback={sendUpdatedParadigmVariables}
        />
      </div>
    </div>
  </div></SetupUIBlock
>

<!-- </div> -->

<style>
  .button-row-div {
    display: flex;
    justify-content: start;
    align-items: end;
    flex-direction: row;
    padding-bottom: 8px;
  }
</style>
