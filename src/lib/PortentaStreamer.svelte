<script>
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { store } from "../../store/stores";
  import { PortentaStreamerTRange } from "../../store/stores";
  import { openWebsocket } from "../monitor_api.js";
  import { scaleLinear } from "d3";

  export let wsEndpointName;
  export let dataStore;
  export let minYData;
  export let maxYData;
  export let height = 300;
  export let title = "placeholder title";

  export let nYTicks = 3;
  export let yTickLabels = null;
  export let yTopOffsetPx = 50;
  export let xLeftOffsetPx = 70;

  let isActive = false;
  let closeCallback = () => {};
  let width = 0;
  let DOMRect = { width: width };

  const recentDataLength = 100;
  const olderDataSubsampling = 10;
  const xRangeSeconds = 3;
  let recentData = [];
  let olderData = [];

  const tickLength = 8;
  const xRightOffsetPx = 20;
  const yBottomOffsetPx = 20;
  const yAxisOffsetPx = 20;
  
  $: if (DOMRect) {
      width = DOMRect.width;
    }

  $: xScale = scaleLinear()
    .domain([$PortentaStreamerTRange.max, $PortentaStreamerTRange.min])
    .range([xLeftOffsetPx, width - xRightOffsetPx]);

  $: yScale = scaleLinear()
    .domain([minYData, maxYData])
    .range([height - yBottomOffsetPx, yTopOffsetPx]);

  $: xTicks = xScale
    .ticks(5)
    .map((tick) => ({ value: tick, position: xScale(tick) }));
  $: yTicks = yScale
    .ticks(nYTicks)
    // .map((tick, i) => ({ value: tick, position: yScale(tick) }));
    .map((tick, i) => ({ value: yTickLabels == null ? tick : yTickLabels[i], position: yScale(tick) }));

  // $: console.log($dataStore);
  // $: console.log($dataStore.length);

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
    $PortentaStreamerTRange.min = newData[newData.length - 1].T;
    $PortentaStreamerTRange.max = $PortentaStreamerTRange.min - xRangeSeconds*1000000;

    // update recentData with new websocket data
    recentData = recentData.concat(newData);
    // find index of first element in olderData that is greater than maxXData
    for (var i = 0; i < recentData.length; i++) {
      if (recentData[i].T > $PortentaStreamerTRange.max) {
        break;
      }
    }
    recentData = recentData.slice(i);

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
        if (olderData[i].T > $PortentaStreamerTRange.max) {
          break;
        }
      }
      // slice olderData to only include data that is greater than maxXData
      olderData = olderData.slice(i);
    }
    $dataStore = olderData.concat(recentData);
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
  <div class="plot-div" bind:contentRect={DOMRect}
  style="height: {isActive ? height : 0}px">
    {#if isActive}

      <svg {width} {height} overflow="visible">
        {#each $dataStore as point, i}
          {#if wsEndpointName === "ballvelocity"}
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
            <!-- fresh package or not -->
            {#if (point.F) == 0}
              <circle
                cx={xScale(point.T)}
                cy={yScale(maxYData)}
                r="3"
                style="fill:var(--accent-color);fill-opacity:.5"
              />
            {/if}
          {/if}

          {#if wsEndpointName === "portentaoutput"}
            {#if point.N === "L"}
              <circle
                cx={xScale(point.T)}
                cy={yScale(1)}
                r="3"
                fill="var(--fg-color)"
              />
              <line
                x1={xScale(point.T)}
                y1={yScale(1)}
                x2={xScale(point.T + point.V)}
                y2={yScale(1)}
                stroke="var(--fg-color)"
                stroke-width="2"
              />
            {/if}
            {#if point.N === "R"}
              <circle
                cx={xScale(point.T)}
                cy={yScale(2)}
                r="3"
                fill="var(--fg-color)"
              />
              <line
                x1={xScale(point.T)}
                y1={yScale(2)}
                x2={xScale(point.T + point.V * 1000)}
                y2={yScale(2)}
                stroke="var(--fg-color)"
                stroke-width="2"
              />
            {/if}
            {#if point.N === "S"}
              <circle
                cx={xScale(point.T)}
                cy={yScale(3)}
                r="3"
                fill="var(--good-color)"
              />
              <line
                x1={xScale(point.T)}
                y1={yScale(3)}
                x2={xScale(point.T + point.V * 1000)}
                y2={yScale(3)}
                stroke="var(--good-color)"
                stroke-width="2"
              />
            {/if}
            {#if point.N === "F"}
              <circle
                cx={xScale(point.T)}
                cy={yScale(3)}
                r="3"
                fill="var(--error-color)"
              />
              <line
                x1={xScale(point.T)}
                y1={yScale(3)}
                x2={xScale(point.T + point.V * 1000)}
                y2={yScale(3)}
                stroke="var(--error-color)"
                stroke-width="2"
              />
            {/if}
            {#if point.N === "A"}
              <circle
                cx={xScale(point.T)}
                cy={yScale(4)}
                r="3"
                fill="var(--fg-color)"
              />
            {/if}
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
        {#if title == "Ball Velocity"}
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
        {/if}
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
    transition: height 0.2s ease-in-out;
  }
  .portenta-stream-card {
    border: 1px solid var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    flex-grow: 1;
    /* max-width: 900px; */
    min-width: 500px;
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
