<script>
  import { store } from "../../store/stores";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import {  openWebsocket } from "../monitor_api.js";

  // websocket
  export let websocketName;
  export let title;
  let closeCallback = () => {};

  // visual properties
  let isActive = false;

  // video properties
  let imageWidth = 640;
  let imageHeight = 0;
  let imageUrl;

  function handleWSHandshakeError(result) {
    console.log("in handleWSHandshakeError");
    closeCallback();
    isActive = false;
    $store.showModal = true;
    $store.modalMessage = "Websocket failed to open. Check server for deatils.";
  }

  function processFrame(wsFrameMessage) {
    imageUrl = URL.createObjectURL(wsFrameMessage.data);
  }

  function updateDimensions(event) {
    imageWidth = event.target.naturalWidth;
    imageHeight = event.target.naturalHeight;
  }

  async function switchCardOnOff(event) {
    if (!isActive) {
      isActive = !isActive;
      closeCallback = openWebsocket(
        websocketName,
        processFrame,
        handleWSHandshakeError
      );
    } else {
      isActive = !isActive;
      closeCallback();
    }
  }
</script>

<div class="monitor-dropdown-card">
  <div id="card-header-div">
    <div>
      <h1>{title}</h1>
    </div>
    <div id="swtich-btn-div">
      <ShowHideCardButton
        onClickCallback={switchCardOnOff}
        showCross={isActive}
      />
    </div>
  </div>
  <div
    class="content-div"
    style="height: {isActive ? imageHeight : 0}px; width:{imageWidth}px"
  >
    {#if isActive}
      <img src={imageUrl} alt="Webcam frame" on:load={updateDimensions} />
    {/if}
  </div>
</div>

<style>
  .monitor-dropdown-card {
    border: 1px solid var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    /* flex-grow: 1; */
    min-width: 300px;
  }
  .content-div {
    transition: height 0.2s ease-in-out;
    margin-top: 5px;
  }
  img {
    border-radius: 5px;
  }
  #card-header-div {
    border-bottom: 1px solid var(--fgFaint-color);
    padding-bottom: 6px;
    display: flex;
    margin-bottom: 20px;
  }
  #card-header-div h1 {
    font-weight: bold;
    font-size: 14pt;
    margin: 0;
    padding: 0;
    color: var(--fg-color);
  }
  #swtich-btn-div {
    flex-grow: 1;
    display: flex;
    justify-content: flex-end;
  }
</style>
