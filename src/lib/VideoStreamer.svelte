<script>
  import { store, globalT } from "../../store/stores";
  import { openWebsocket, time2str } from "../monitor_api.js";

  import ShowHideCardButton from "./ShowHideCardButton.svelte";

  export let websocketName;
  export let title;

  let closeCallback = () => {};
  let ws;
  let isActive = false;

  let prvGlobalT = 0;
  let timestamp = "";
  let imagePackage = {};

  // video properties
  let imageWidth = 240;
  let imageHeight = 0;
  let imageUrl;
  let previousImageUrl;

  function handleWSHandshakeError(result) {
    console.log("in handleWSHandshakeError");
    closeCallback();
    isActive = false;
    $store.showModal = true;
    $store.modalMessage = "Websocket failed to open. Check server for details.";
  }

  function processFrameMessage(wsFrameMessage) {
    // Revoke the previous object URL to free up memory
    if (previousImageUrl) {
      URL.revokeObjectURL(previousImageUrl);
    }
    // the acutal image data
    if (wsFrameMessage.data instanceof Blob) {
      imageUrl = URL.createObjectURL(wsFrameMessage.data);
      previousImageUrl = imageUrl;
      // metadata
    } else {
      imagePackage = JSON.parse(wsFrameMessage.data);
      const lag = $globalT - imagePackage.PCT;
      if (lag > 500000) {
        console.log(`${websocketName} lag!`, lag / 1e6, "s");
      }
      timestamp = time2str(imagePackage.PCT / 1000);
    }
  }

  function updateDimensions(event) {
    imageWidth = event.target.naturalWidth;
    imageHeight = event.target.naturalHeight;
  }

  async function switchCardOnOff(event) {
    if (!isActive) {
      isActive = !isActive;
      const result = openWebsocket(
        websocketName,
        processFrameMessage,
        handleWSHandshakeError,
        $store.initiated
      );

      if (Array.isArray(result)) {
        [closeCallback, ws] = result;
      } else {
        closeCallback = result;
      }
    } else {
      isActive = !isActive;
      closeCallback();
      imageWidth = 240;
    }
  }

  $: if (
    $store.initiatedInspect &&
    isActive &&
    ws.readyState === 1 &&
    $globalT !== prvGlobalT
  ) {
    ws.send($globalT);
    prvGlobalT = $globalT;
  }
</script>

<div class="monitor-dropdown-card" style="width:{imageWidth}px">
  <div id="card-header-div">
    <div id="label-headers-div">
      <h1>{title}</h1>
    </div>
    {#if isActive}
      <div id="timestamp-headers-div">
        <h1>{timestamp}</h1>
      </div>
    {/if}

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
    max-width: 900px;
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
  #label-headers-div h1 {
    font-weight: bold;
    font-size: 14pt;
    margin: 0;
    padding: 0;
    color: var(--fg-color);
  }
  #timestamp-headers-div h1 {
    font-size: 12pt;
    margin-left: 1em;
    font-family: "Courier New", Courier, monospace;
    color: var(--fg-color);
  }
  #timestamp-headers-div {
    flex-grow: 12;
    display: flex;
    justify-content: flex-end;
  }
  #swtich-btn-div {
    flex-grow: 1;
    display: flex;
    justify-content: flex-end;
  }
</style>
