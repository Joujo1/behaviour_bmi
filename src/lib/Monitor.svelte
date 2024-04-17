<script>
  import store from "../../store/store";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import SetupUIInput from "./SetupUIInput.svelte";
  import {POSTUnityInput} from "../monitor_api.js";

  let successLengthTextValue = 100;
  let successDelayTextValue = 100;
  let punishmentLengthTextValue = 100;
  let teleportXTextValue = 0;
  let teleportZTextValue = 0;
  let teleportAngleTextValue = 0;
  
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
    const unityMsg = `Success,${successLengthTextValue},${successDelayTextValue}`
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendFailure() {
    const unityMsg = "Failure"
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendPunishment() {
    const unityMsg = `Punishment,${punishmentLengthTextValue}`
    const result = await POSTUnityInput(unityMsg)
    handlePOSTResult(result)
  }
  async function sendTeleport() {
    const unityMsg = `Teleport,${teleportXTextValue},${teleportZTextValue},${teleportAngleTextValue}`
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
        <SetupUIInput bind:value={successLengthTextValue} tooltip="opened-for [ms]"></SetupUIInput>
        <SetupUIInput bind:value={successDelayTextValue} tooltip="delay [ms]"></SetupUIInput>
        
        
        <div class="right-aligned">

          <SetupUIButton
          label="Failure"
          onClickCallback={sendFailure}
          
          />
        </div>
      </div>



      <div class="button-row-div">
      <SetupUIButton
      label="Punishment"
      onClickCallback={sendPunishment}
      />
      <SetupUIInput bind:value={punishmentLengthTextValue} tooltip="length [ms]"></SetupUIInput>
      </div>
      
      <div class="button-row-div">
        <SetupUIButton
          label="Teleport"
          onClickCallback={sendTeleport}
        />
        <SetupUIInput bind:value={teleportXTextValue} tooltip="X position"></SetupUIInput>
        <SetupUIInput bind:value={teleportZTextValue} tooltip="Z position"></SetupUIInput>
        <SetupUIInput bind:value={teleportAngleTextValue} tooltip="Angle"></SetupUIInput>
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
