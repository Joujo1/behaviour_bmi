<script>
  import store from "../../store/store";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import MonitorDropdown from "./MonitorDropdown.svelte";
  import MonitorInputField from "./MonitorInputField.svelte";
  import { POSTUnityInput } from "../monitor_api.js";
  import { GETParadigms } from "../monitor_api.js";
  import { GETAnimals } from "../monitor_api.js";
  import { POSTAnimal } from "../monitor_api.js";
  import { POSTAnimalWeight } from "../monitor_api.js";
  import { onMount } from "svelte";

  let paradigms = [];
  let paradigmSelection;
  let animals = [];
  let animalSelection;
  let animalWeight;

  function handlePOSTResult(result) {
    console.log(result);
    if (result !== true) {
      $store.showModal = true;
      $store.modalMessage = result;
    }
  }

  async function getParadigms() {
    paradigms = await GETParadigms();
  }
  onMount(getParadigms);

  async function getAnimals() {
    animals = await GETAnimals();
  }
  onMount(getAnimals);

  async function startSession() {
    if (!paradigmSelection) {
      $store.showModal = true;
      $store.modalMessage = "Please select a paradigm";
      return;
    }
    if (!animalSelection) {
      $store.showModal = true;
      $store.modalMessage = "Please select an animal";
      return;
    }
    if (!animalWeight) {
      $store.showModal = true;
      $store.modalMessage = "Please enter the animal weight";
      return;
    }
    let unityMsg = `Paradigm,${paradigmSelection}`.slice(0, -5);
    let result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);

    result = await POSTAnimal(animalSelection);
    handlePOSTResult(result);
    result = await POSTAnimalWeight(animalWeight);
    handlePOSTResult(result);

    unityMsg = "Start";
    result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
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
</script>

<div id="setup-div" class={$store.showMonitor ? "" : "hide"}>
  <SetupUIBlock>
    <div slot="header">Session Initiation</div>
    <div slot="setupui">
      <div class="button-row-div">
        <MonitorDropdown
          label="Paradigm"
          bind:value={paradigmSelection}
          isEnabled={!$store.unitySessionRunning}
          options={paradigms}
          getOptions={getParadigms}
        />
      </div>
      <div class="button-row-div">
        <MonitorDropdown
          label="Animal"
          bind:value={animalSelection}
          isEnabled={!$store.unitySessionRunning}
          options={animals}
          getOptions={getAnimals}
        />
      </div>
      <div class="button-row-div">
        <MonitorInputField
          label="Weight [g]"
          isEnabled={!$store.unitySessionRunning}
          tooltip="Animal weight in grams"
          bind:value={animalWeight}
        />
      </div>

      <div class="button-row-div">
        <SetupUIButton label="Airvalve" onClickCallback={sendAirvalve} />
        <SetupUIButton
          label="Start Session"
          onClickCallback={startSession}
          isEnabled={!$store.unitySessionRunning}
        />
        <SetupUIButton
          label="Stop Session"
          onClickCallback={stopSession}
          isEnabled={$store.unitySessionRunning}
        />
      </div>
  </div></SetupUIBlock>
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
