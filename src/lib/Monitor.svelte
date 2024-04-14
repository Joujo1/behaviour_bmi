<script>
  import store from "../../store/store";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import SetupUIInput from "./SetupUIInput.svelte";
  import {POSTUnityInput} from "../monitor_api.js";

  let textValueOne = 0;
  let textValueTwo = 0;
  let textValueThree = 0;
  
  function handlePOSTResult(result) {
    console.log(result);
    if (result !== true) {
      $store.showModal = true;
      $store.modalMessage = result;
    }
  }

  async function startSession() {
    const unityMsg = "Start"
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function stopSession() {
    const unityMsg = "Stop"
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendAirvalve() {
    const unityMsg = "Airvalve"
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendSucess() {
    const unityMsg = `Success,${textValueOne},${textValueTwo}`
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendFailure() {
    const unityMsg = "Failure"
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendPunishment() {
    const unityMsg = `Punishment,${textValueOne}`
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendTeleport() {
    const unityMsg = `Teleport,${textValueOne},${textValueTwo},${textValueThree}`
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
</script>

<div id="setup-div" class={$store.showMonitor ? "" : "hide"}>
  <SetupUIBlock>
    <div slot="header">Manual interface</div>
    <div slot="setupui">
      <div class="button-row-div">
        <SetupUIButton
          label="Start Session"
          onClickCallback={startSession}
        />
        <SetupUIButton
          label="Stop Session"
          onClickCallback={stopSession}
        />
        <SetupUIButton
          label="Airvalve"
          onClickCallback={sendAirvalve}
        />
      </div>
      <div class="button-row-div">
        <SetupUIButton
          label="Success"
          onClickCallback={sendSucess}
        />
        <SetupUIButton
          label="Failure"
          onClickCallback={sendFailure}
        />
        <SetupUIButton
          label="Punishment"
          onClickCallback={sendPunishment}
        />
      </div>
      <div class="button-row-div">
        <SetupUIButton
          label="Teleport"
          onClickCallback={sendTeleport}
        />
      </div>
      <div class="button-row-div">
        <SetupUIInput bind:value={textValueOne}></SetupUIInput>
        <SetupUIInput bind:value={textValueTwo}></SetupUIInput>
        <SetupUIInput bind:value={textValueThree}></SetupUIInput>
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
</style>
