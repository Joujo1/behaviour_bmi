<script>
  import { store } from "../../store/stores";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { openWebsocket } from "../monitor_api.js";
  import { line, scaleLinear } from "d3";
  import { derived } from "svelte/store";
  import { fly } from "svelte/transition";
  import { cubicOut } from "svelte/easing";

  export let wsEndpointName;
  export let dataStore;
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
  
  let wsOnMessageCallback = (msg) => {
    let newData = JSON.parse(msg.data)

    minXData = newData[newData.length-1].T
    
    dataStore.update(data => data
      .concat(newData)
      .filter((datapoint, i) => datapoint.T > minXData-xRangeSeconds*1000000)
    )
    maxXData = $dataStore[0].T
    // console.log($dataStore)
    // console.log(minXData)
    // console.log(maxXData)
  }

  function switchCardOnOff(event) {
    isActive = !isActive;
    if (isActive) {
      closeCallback = openWebsocket(wsEndpointName, wsOnMessageCallback, 
                                    handleWSHandshakeError);
    } 
    else {
      closeCallback();
      dataStore.set([]);
    }
  }

  $: if (DOMRect) {
    width = DOMRect.width;
  }


  let dataPoints = [];

  $: dataStore.subscribe((value) => {
    console.log("dataStore changed");
    console.log(value);
    dataPoints = value;
  });

  // let linePath = "";

  // $: dataStore.subscribe(data => {
  //     const lineGenerator = line()
  //         .x(d => xScale(d.T))
  //         .y(d => yScale(d.pitch));

  //     linePath = lineGenerator(data);
  // });


  let xRangeSeconds = 2;
  let minYData = -20;
  let maxYData = 20;
  let minXData = 0;
  let maxXData = 10;
  let dataQueue = [];

  const xLeftOffsetPx = 20;
  const xRightOffsetPx = 20;
  const yTopOffsetPx = 20;
  const yBottomOffsetPx = 20;

  $: xScale = scaleLinear() 
    .domain([maxXData,minXData])
    .range([xLeftOffsetPx, width-xRightOffsetPx]);
  
  $: yScale = scaleLinear() 
    .domain([minYData, maxYData])
    .range([height-yTopOffsetPx, yBottomOffsetPx]);
  
  $: xTicks = xScale.ticks().map(tick => ({ value: tick, position: xScale(tick) }));
  $: yTicks = yScale.ticks().map(tick => ({ value: tick, position: yScale(tick) }));
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
  <svg width={width} height={height}>
    {#each dataPoints as point (point.T)}
      <circle cx={xScale(point.T)} cy={yScale(point.pitch)} r="5" fill="red" />
    {/each}
  
    <!-- X Axis -->
    <line x1="0" y1={height - yBottomOffsetPx} x2={width} y2={height - yBottomOffsetPx} stroke="black" />
    {#each xTicks as { value, position }}
      <line x1={position} y1={height - yBottomOffsetPx} x2={position} y2={height - yBottomOffsetPx + 10} stroke="black" />
      <text x={position} y={height - yBottomOffsetPx + 20} text-anchor="middle">{value}</text>
    {/each}
  
    <!-- Y Axis -->
    <line x1="0" y1="0" x2="0" y2={height - yBottomOffsetPx} stroke="black" />
    {#each yTicks as { value, position }}
      <line x1="0" y1={position} x2="-10" y2={position} stroke="black" />
      <text x="-20" y={position} text-anchor="end" dominant-baseline="middle">{value}</text>
    {/each}
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
