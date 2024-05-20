<script>
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { store } from "../../store/stores";
  import { openWebsocket } from "../monitor_api.js";
  import { scaleLinear } from "d3";

  export let wsEndpointName;
  export let dataStore;
  export let minYData;
  export let maxYData;
  export let height = 300;
  export let title = "placeholder title";

  function handleWSHandshakeError(result) {
    console.log("in handleWSHandshakeError");
    closeCallback();
    isActive = false;
    $store.showModal = true;
    $store.modalMessage = "Websocket failed to open. Check server for deatils.";
  }
  
  // update dataStore with new websocket data 
  function wsOnMessageCallback(msg) {
    let newData = JSON.parse(msg.data);
    minXData = newData[newData.length - 1].T;
    maxXData = minXData - xRangeSeconds*1000000;

    // update recentData with new websocket data
    recentData = recentData.concat(newData);
    if (recentData.length > recentDataLength) {
      var nSurplus = recentData.length - recentDataLength;
      var surplusData = recentData.slice(0, nSurplus);
      recentData = recentData.slice(nSurplus);

      // subsample surplus data
      olderData = olderData.concat(
        surplusData.filter((_, i) => i % olderDataSubsampling === 0)
      );

      // find index of first element in olderData that is greater than maxXData
      for (var i = 0; i < olderData.length; i++) {
        if (olderData[i].T > maxXData) {
          break;
        }
      }
      // slice olderData to only include data that is greater than maxXData
      olderData = olderData.slice(i);
      $dataStore = olderData.concat(recentData);
    }
  }

  function switchCardOnOff(event) {
    isActive = !isActive;
    if (isActive) {
      closeCallback = openWebsocket(
        wsEndpointName,
        wsOnMessageCallback,
        handleWSHandshakeError
      );
    } else {
      closeCallback();
      dataStore.set([]);
    }
  }

  $: if (DOMRect) {
    width = DOMRect.width;
  }

  let isActive = false;
  let closeCallback = () => {};
  let width = 0;
  let DOMRect = { width: width };

  const recentDataLength = 100;
  const olderDataSubsampling = 5;
  const xRangeSeconds = 5;
  let recentData = [];
  let olderData = [];

  let minXData = -1;
  let maxXData = -1;
  
  const tickLength = 8;
  const xLeftOffsetPx = 70;
  const xRightOffsetPx = 20;
  const yTopOffsetPx = 50;
  const yBottomOffsetPx = 20;
  const yAxisOffsetPx = 20;

  $: xScale = scaleLinear()
    .domain([maxXData, minXData])
    .range([xLeftOffsetPx, width - xRightOffsetPx]);

  $: yScale = scaleLinear()
    .domain([minYData, maxYData])
    .range([height - yBottomOffsetPx, yTopOffsetPx]);

  $: xTicks = xScale
    .ticks(5)
    .map((tick) => ({ value: tick, position: xScale(tick) }));

  $: yTicks = yScale
    .ticks(5)
    .map((tick) => ({ value: tick, position: yScale(tick) }));
</script>

<div class="portenta-stream-card">
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
  <div class="plot-div" bind:contentRect={DOMRect}>
    <slot name="plotarea"></slot>
    {#if isActive}
      <svg {width} {height} overflow="visible">
        {#each $dataStore as point, i}
          {#if title === "Ball Velocity"}
            <circle
              cx={xScale(point.T)}
              cy={yScale(point.pitch)}
              r="2"
              stroke="var(--fg-color)"
              stroke-width="1.5"
              fill="none"
            />
            <circle
              cx={xScale(point.T)}
              cy={yScale(point.raw)}
              r="3"
              fill="var(--fg-color)"
            />
            <circle
              cx={xScale(point.T)}
              cy={yScale(point.yaw)}
              r="3"
              fill="#888888"
            />
          {/if}
          {#if title === "Lick Sensor"}
            <circle
              cx={xScale(point.T)}
              cy={yScale(point.V)}
              r="3"
              fill="var(--fg-color)"
            />
          {/if}
        {/each}

        <!-- X Axis -->
        <!-- main axis line -->
        <line
          x1={xLeftOffsetPx}
          y1={height - yBottomOffsetPx}
          x2={width}
          y2={height - yBottomOffsetPx}
          stroke-width="1"
          stroke="var(--fgFaint-color)"
        />
        {#each xTicks as { value, position }}
          <!-- x ticks -->
          <line
            x1={position}
            y1={height - yBottomOffsetPx}
            x2={position}
            y2={height - yBottomOffsetPx + tickLength}
            stroke-width="1"
            stroke="var(--fgFaint-color)"
          />
          <!-- x tick labels -->
          <text
            x={position}
            y={height - yBottomOffsetPx + tickLength + 17}
            fill="var(--fg-color)"
            text-anchor="middle">{(value / 1e6).toLocaleString()}</text
          >
        {/each}

        <!-- x label background box: [s] -->
        <rect
          x={xLeftOffsetPx - yAxisOffsetPx - 15}
          y={height - yBottomOffsetPx + 1}
          width={60}
          height={30}
          fill="var(--bg-color)"
        />
        <!-- x label: [s] -->
        <text
          x={xLeftOffsetPx}
          y={height - yBottomOffsetPx + tickLength + 17}
          font-size={18}
          fill="var(--fg-color)"
          text-anchor="middle"
        >
          {"[s]"}</text
        >

        <!-- Y Axis -->
        <!-- Y label: [a.u.] -->
        <text
          x={xLeftOffsetPx - tickLength - yAxisOffsetPx - 7}
          y={yTopOffsetPx - 30}
          font-size={18}
          text-anchor="end"
          fill="var(--fg-color)"
          dominant-baseline="middle"
        >
          {"[a.u.]"}</text
        >
        <!-- x axis line -->
        <line
          x1={xLeftOffsetPx - yAxisOffsetPx}
          y1={yTopOffsetPx}
          x2={xLeftOffsetPx - yAxisOffsetPx}
          y2={height - yBottomOffsetPx}
          stroke-width="1"
          stroke="var(--fgFaint-color)"
        />
        {#each yTicks as { value, position }}
          <!-- x axis ticks -->
          <line
            x1={xLeftOffsetPx - yAxisOffsetPx}
            y1={position}
            x2={xLeftOffsetPx - tickLength - yAxisOffsetPx}
            y2={position}
            stroke="var(--fgFaint-color)"
          />

          <!-- x axis tick labels -->
          <text
            x={xLeftOffsetPx - tickLength - yAxisOffsetPx - 7}
            y={position}
            text-anchor="end"
            dominant-baseline="middle"
            fill="var(--fg-color)">{value}</text
          >
        {/each}
      </svg>
    {/if}
  </div>
</div>

<style>
  .plot-div {
    padding: 5px;
    /* max-width: max-content; */
    /* min-width: 400px; */

    /* display: flex;
    justify-content: center;
    flex-shrink: 1; */
  }
  .portenta-stream-card {
    border: 1px solid var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    flex-grow: 1;
    max-width: 900px;
    min-width: 500px;
  }
  #card-header-div {
    border-bottom: 1px solid var(--fgFaint-color);
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
