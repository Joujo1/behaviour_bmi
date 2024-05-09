<script>
  import { store } from "../../store/stores";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import MonitorDropdown from "./MonitorDropdown.svelte";
  import MonitorInputField from "./MonitorInputField.svelte";
  import BigTextInput from "./BigTextInput.svelte";
  import { POSTUnityInput } from "../monitor_api.js";
  import { GETParadigms } from "../monitor_api.js";
  import { GETAnimals } from "../monitor_api.js";
  import { POSTAnimal } from "../monitor_api.js";
  import { POSTAnimalWeight } from "../monitor_api.js";
  import { POSTSessionNotes } from "../monitor_api.js";
  import { onMount } from "svelte";

  let paradigms = [];
  let paradigmSelection;
  let animals = [];
  let animalSelection;
  let animalWeight;
  let freeNotes = "Free notes here";

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
    let result = await POSTSessionNotes(freeNotes);
    handlePOSTResult(result);

    const unityMsg = "Stop";
    result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
  async function sendAirvalve() {
    const unityMsg = "Airvalve";
    const result = await POSTUnityInput(unityMsg);
    handlePOSTResult(result);
  }
</script>

<SetupUIBlock>
  <div slot="header">Session Initiation</div>
  <div slot="setupui">
    <div class="columns-div">
      <div class="button-column-div">
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
      </div>
      <div class="button-column-div">
        <BigTextInput bind:value={freeNotes} isEnabled={true} />
      </div>
    </div>
    <div class="button-row-div">
      <SetupUIButton
        label="Airvalve"
        onClickCallback={sendAirvalve}
        isEnabled={!$store.unitySessionRunning}
      />
      <SetupUIButton
        label="StartSession"
        onClickCallback={startSession}
        isEnabled={!$store.unitySessionRunning}
      />
      <div class="right-aligned">
        <SetupUIButton
          label="StopSession"
          onClickCallback={stopSession}
          isEnabled={$store.unitySessionRunning}
        />
      </div>
    </div>
  </div></SetupUIBlock
>

<style>
  .columns-div {
    display: flex;
  }
  .button-row-div {
    display: flex;
    justify-content: start;
    align-items: end;
    flex-direction: row;
    padding-bottom: 3px;
  }

  .button-column-div {
    display: flex;
    flex-direction: column;
  }

  .right-aligned {
    margin-left: auto;
  }
</style>
