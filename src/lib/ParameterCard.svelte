<script>
  import { store } from "../../store/stores";
  import UploadButton from "./UploadButton.svelte";
  import {PATCHParameter} from "../setup_api.js";

  export let titleParams = "Card Title";
  export let cardParams = {};
  export let lockedParams = {};

  let newInput = false;
  let updatedParams = {};

  const maxKeyLength = Math.max(
    ...Object.keys(cardParams).map((key) => key.length)
  );
  const maxValueLength = Math.min(
    30,
    Math.max(...Object.values(cardParams).map((v) => String(v).length))
  );
  const width = 11 * (maxKeyLength + maxValueLength) + 20;
  const highlightedParams = ["SESSION_NAME_POSTFIX", "LOGGING_LEVEL"];

  async function uploadParameters(event) {
    // Iterate over each updated parameter and send a PATCH request
    for (let key in updatedParams) {
      const result = await PATCHParameter(key, updatedParams[key])
      
      if (result === true) {
        cardParams[key] = updatedParams[key];
        delete updatedParams[key];
        newInput = Object.keys(updatedParams).length === 0 ? false : true;
      } else {
        $store.showModal = true;
        $store.modalMessage = result;
        // event.target.value = cardParams[key];
      }
    }
    console.log(updatedParams);
    console.log(updatedParams);
  }

  function handleInput(event) {
    let newValue = event.target.value;
    // console.log(newValue, cardParams[event.target.id])
    // check if the provided input differs from the default value
    if (newValue != cardParams[event.target.id]) {
      newInput = true;
      // keep track of changed parameters
      updatedParams[event.target.id] = newValue;
    } else {
      // if the input goes abck to the default remove it gain
      delete updatedParams[event.target.id];
      // new input might still be true if other inputs are unqiue from default
      newInput = Object.keys(updatedParams).length === 0 ? false : true;
    }
    // console.log(updatedParams, newInput)
  }
</script>

<div class="parameter-card" style=" min-width: {width}px; max-width:800px">
  <div id="card-header-div">
    <div>
      <h1>{titleParams}</h1>
    </div>
    <div id="upload-btn-div">
      <UploadButton onClickCallback={uploadParameters} {newInput} />
    </div>
  </div>
  <div id="card-content-div">
    {#each Object.entries(cardParams) as [key, value]}
      <div class="single-parameter-div">
        <p>{key}</p>
        <div
          class={!highlightedParams.includes(key)
            ? "input-field"
            : "input-field-highlighted"}
        >
          <input
            id={key}
            type="text"
            {value}
            on:input={handleInput}
            on:keydown={(event) => {
              if (event.key === 'Enter') {
                uploadParameters(event);
              }
            }}
            disabled={lockedParams.includes(key)}
            style="min-width: {11 * maxValueLength}px; border-radius: 5px;"
          />
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  .parameter-card {
    background-color: var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    flex-grow: 1;
  }
  #card-header-div {
    border-bottom: 1px solid var(--fg-color);
    padding-bottom: 12px;
    display: flex;
  }
  #card-header-div h1 {
    font-weight: bold;
    font-size: 14pt;
    margin: 0;
    padding: 0;
    color: var(--fg-color);
  }
  #upload-btn-div {
    flex-grow: 1;
    display: flex;
    justify-content: flex-end;
  }

  #card-content-div {
    flex-direction: column;
    padding-bottom: 8px;
  }
  .single-parameter-div {
    font-family: monospace;
    font-size: 12pt;
    display: flex;
    justify-content: space-between;
    height: 26px;
  }
  .single-parameter-div input {
    font-family: monospace;
    font-size: 12pt;
    height: 18px;
    border: none;
    /* background-color: white; */
    /* color: black; */
    background-color: var(--bg-color);
    color: var(--fg-color);
  }
  .input-field {
    margin-top: 12px;
  }
  .input-field-highlighted {
    margin-top: 12px;
    border: var(--accent-color) 2px solid;
    border-radius: 5px;
  }
  .input-field input:disabled {
    color: gray;
  }
</style>
