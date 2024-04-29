<script>
  import store from "../../store/store";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import SetupUIInput from "./SetupUIInput.svelte";
  import MonitorDropdown from "./MonitorDropdown.svelte";
  import MonitorInputField from "./MonitorInputField.svelte";
  import { POSTUnityInput } from "../monitor_api.js";
  import { GETParadigms } from "../monitor_api.js";
  import { GETAnimals } from "../monitor_api.js";
  import { POSTAnimal } from "../monitor_api.js";
  import { POSTAnimalWeight } from "../monitor_api.js";
  import { onMount } from "svelte";

  let successLengthTextValue = 100;
  let successDelayTextValue = 100;
  let punishmentLengthTextValue = 100;
  let teleportXTextValue = 0;
  let teleportZTextValue = 0;
  let teleportAngleTextValue = 0;
  let distanceDelta = 1;
  let angleDelta = 5;

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
  async function sendTeleport() {
    const unityMsg = `Teleport,${teleportXTextValue},${teleportZTextValue},${teleportAngleTextValue}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendDistanceDelta() {
    const unityMsg = `TrialEndTeleportDistanceDelta,${distanceDelta}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendAngleDelta() {
    const unityMsg = `TrialEndTeleportAngleDelta,${angleDelta}`;
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
</script>

<div id="setup-div" class={$store.showMonitor ? "" : "hide"}>
  <SetupUIBlock>
    <div slot="header">Session Interference</div>
    <div slot="setupui">
      <div class="button-row-div">
        <SetupUIButton
          label="Success"
          onClickCallback={sendSucess}
          isEnabled={$store.unitySessionRunning}
        />
        <SetupUIInput
          bind:value={successLengthTextValue}
          isEnabled={$store.unitySessionRunning}
          tooltip="opened-for [ms]"
        ></SetupUIInput>
        <SetupUIInput
          bind:value={successDelayTextValue}
          isEnabled={$store.unitySessionRunning}
          tooltip="delay [ms]"
        ></SetupUIInput>
        <div class="right-aligned">
          <SetupUIButton
            label="Failure"
            onClickCallback={sendFailure}
            isEnabled={$store.unitySessionRunning}
          />
        </div>
      </div>

      <div class="button-row-div">
        <SetupUIButton
          label="Punishment"
          onClickCallback={sendPunishment}
          isEnabled={$store.unitySessionRunning}
        />
        <SetupUIInput
          bind:value={punishmentLengthTextValue}
          isEnabled={$store.unitySessionRunning}
          tooltip="length [ms]"
        ></SetupUIInput>
      </div>

      <div class="button-row-div">
        <SetupUIButton
          label="Teleport"
          onClickCallback={sendTeleport}
          isEnabled={$store.unitySessionRunning}
        />
        <SetupUIInput
          bind:value={teleportXTextValue}
          isEnabled={$store.unitySessionRunning}
          tooltip="X position"
        ></SetupUIInput>
        <SetupUIInput
          bind:value={teleportZTextValue}
          isEnabled={$store.unitySessionRunning}
          tooltip="Z position"
        ></SetupUIInput>
        <SetupUIInput
          bind:value={teleportAngleTextValue}
          isEnabled={$store.unitySessionRunning}
          tooltip="Angle"
        ></SetupUIInput>
      </div>

      <div class="button-row-div">
        <SetupUIButton
          label="DistanceDelta"
          onClickCallback={sendDistanceDelta}
          isEnabled={$store.unitySessionRunning}
        />
        <SetupUIInput
          bind:value={distanceDelta}
          isEnabled={$store.unitySessionRunning}
          tooltip="Delta pillar distance for next trials"
        ></SetupUIInput>
        <SetupUIButton
          label="AngleDelta"
          onClickCallback={sendAngleDelta}
          isEnabled={$store.unitySessionRunning}
        />
        <SetupUIInput
          bind:value={angleDelta}
          isEnabled={$store.unitySessionRunning}
          tooltip="Delta pillar angle for next trials"
        ></SetupUIInput>
      </div>
    </div></SetupUIBlock
  >
</div>

<style>
  .button-row-div {
    display: flex;
    justify-content: start;
    align-items: end;
    flex-direction: row;
    padding-bottom: 8px;
  }

  .right-aligned {
    margin-left: auto;
  }
</style>
