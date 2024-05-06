<script>
  import store from "../../store/store";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { openWebsocket } from "../monitor_api.js";
  import { scaleLinear } from "d3";
  import { onMount } from "svelte";

  export let wsEndpointName;
  export let wsOnMessageCallback;
  export let height = 200;
  export let title = "placeholder title";

  let isActive = false;
  let closeCallback = () => {};
  let width = 0
  let DOMRect = {width: width};

  function handleWSHandshakeError(result) {
    console.log("in handleWSHandshakeError");
    closeCallback();
    isActive = false;
    $store.showModal = true;
    $store.modalMessage = "Websocket failed to open. Check server for deatils.";
  }

  function switchCardOnOff(event) {
    isActive = !isActive;
    if (isActive) closeCallback = openWebsocket(wsEndpointName, wsOnMessageCallback, 
                                                handleWSHandshakeError);
    else closeCallback();
  }

  $: if (DOMRect) {
    width = DOMRect.width;
  }




  let xSecondsPast = -5;
  let minYData = -20;
  let maxYData = 20;

  $: xScale = scaleLinear() 
    .domain([0, 10])
    .range([0, width]);
  
  $: yScale = scaleLinear() 
    .domain([minYData, maxYData])
    .range([height, 0]);






</script>

<div class="portenta-stream-card" >
  <div id="card-header-div">
    <div>
      <h1>{title} {DOMRect.width}</h1>
    </div>
    <div id="swtich-btn-div">
      <ShowHideCardButton onClickCallback={switchCardOnOff} showCross={isActive}/>
    </div>
  </div>
  <div class="plot-div" bind:contentRect={DOMRect}
  >
  <slot name="plotarea"></slot>
  {#if isActive}
    <svg
      width={width}
      height={height}
      >
    <circle cx={xScale(0)} cy={yScale(-20)} r="5" fill="red" />
    <circle cx={xScale(1)} cy={yScale(-10)} r="5" fill="red" />
    <circle cx={xScale(5)} cy={yScale(0)} r="5" fill="red" />
    <circle cx={xScale(8)} cy={yScale(20)} r="5" fill="red" />
    <circle cx={xScale(10)} cy={yScale(20)} r="5" fill="red" />
    </svg>
  {/if}
</div>

</div>


<style>
  svg {
    /* background:  */
  }
  .plot-div {
    padding: 5px;
    /* max-width: max-content; */
    /* min-width: 400px; */

    /* display: flex;
    justify-content: center;
    flex-shrink: 1; */
  }
  .portenta-stream-card {
    background-color: var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    flex-grow: 1;
    max-width: 900px;
    min-width: 500px;

  }
  #card-header-div {
    border-bottom: 1px solid var(--fg-color);
    padding-bottom: 6px;
    display: flex;
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
