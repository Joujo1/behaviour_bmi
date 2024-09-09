<script>
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { store, globalT } from "../../store/stores";
  import { PortentaStreamerTRange } from "../../store/stores";
  import { openWebsocket, time2str } from "../monitor_api.js";
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
  let ws;

  let showForward = true;
  let showSideways = false;
  let showRotation = false;

  let fromTimestamp;
  let toTimestamp;

  let prvGlobalT = 0;
  let deltaT2globalT = {};

  let width = 0;
  let DOMRect = { width: width };

  const olderDataSubsampling = 10; // subsample older data, every nth datapoint for xRangeSeconds
  const xRangeSeconds = 3;

  const tickLength = 8;
  const xRightOffsetPx = 20;
  const yBottomOffsetPx = 20;
  const yAxisOffsetPx = 20;

  function handleWSHandshakeError(result) {
    console.log("in handleWSHandshakeError");
    closeCallback();
    isActive = false;
    $store.showModal = true;
    $store.modalMessage = "Websocket failed to open. Check server for deatils.";
  }

  function sliceData2Range() {
    $dataStore = $dataStore.filter((d, idx) => {
      return (
        d.PCT > $PortentaStreamerTRange.max && 
        (d.PCT < $PortentaStreamerTRange.min || $store.initiated) // live data doesn't work as expected with .min ... ; not strictly needed anyway
      );
    });

    if ($dataStore.length) {
      fromTimestamp = time2str($dataStore[0].PCT / 1000);
      toTimestamp = time2str($dataStore[$dataStore.length - 1].PCT / 1000);
    } else {
      fromTimestamp = "";
      toTimestamp = "No data within interval";
    }
    console.debug(wsEndpointName, " dataStore length: ", $dataStore.length);
  }

  function wsOnMessageCallback(msg) {
    let newData = JSON.parse(msg.data);
    if (wsEndpointName == "ballvelocity") {
      newData = newData.filter((d, idx) => {
        return idx % olderDataSubsampling === 0 || d.F === 0;
      });
    }
    
    // update dataStore with new websocket data
    $dataStore.push(...newData);
    // console.log(
    //   "datastore currently: ",
    //   time2str($dataStore[0].PCT / 1000),
    //   time2str($dataStore[$dataStore.length - 1].PCT / 1000)
    // );

    // for live data, update min and max, instead of based on glabalT
    if ($store.initiated) {
      $PortentaStreamerTRange.min = newData[newData.length - 1].PCT; // newest datapoint, minimum deltatime to t0
      $PortentaStreamerTRange.max = $PortentaStreamerTRange.min - xRangeSeconds * 1e6;
    }
    sliceData2Range();
  }

  function switchCardOnOff(event) {
    isActive = !isActive;
    if (isActive) {
      const result = openWebsocket(
        wsEndpointName,
        wsOnMessageCallback,
        handleWSHandshakeError,
        $store.initiated
      );
      if (Array.isArray(result)) {
        [closeCallback, ws] = result;
      } else {
        closeCallback = result;
      }
    } else {
      closeCallback();
      dataStore.set([]);
    }
  }

  // update dataStore boundaries based on globalT (set in SessionTimeline)
  $: if ($store.initiatedInspect) {
    $PortentaStreamerTRange.max = $globalT - (xRangeSeconds * 1e6) / 2;
    $PortentaStreamerTRange.min = $globalT + (xRangeSeconds * 1e6) / 2;
  }

  // send request for new data if all conditions are met
  $: if (
    $store.initiatedInspect &&
    isActive &&
    ws.OPEN &&
    ws.readyState === 1 &&
    $globalT !== prvGlobalT
  ) {
    const diff = Math.abs($globalT - prvGlobalT) / 1e3;
    // user clicked on timeline, very differnt data needs to be requested
    let msg = "0,0";
    if (diff > 100) {
      prvGlobalT = $globalT;
      msg =
        ($globalT - (xRangeSeconds * 1e6) / 2).toString() +
        "," +
        ($globalT + (xRangeSeconds * 1e6) / 2).toString();
      console.log(
        "Big time jump, filling interval xRangeSeconds: ",
        xRangeSeconds
      );
    } else {
      msg =
        (prvGlobalT + (xRangeSeconds * 1e6) / 2).toString() +
        "," +
        ($globalT + (xRangeSeconds * 1e6) / 2).toString();
    }

    // send request for new data
    ws.send(msg);
    console.debug("Sent request for portentadata ms: ", diff);
    prvGlobalT = $globalT;
    sliceData2Range();
  }
  
  // check if any new data is a lick or reward, and play sound
  $: if ($store.initiatedInspect && $dataStore.length) {
    if (wsEndpointName == "portentaoutput") {
      $dataStore.forEach((d) => {
        const newDeltaT = d.PCT - $globalT;
        if (newDeltaT - 0 > 0) {
          deltaT2globalT[d.ID + d.N] = newDeltaT;
        } else {
          // remove that d.id from deltaT2globalT
          if (deltaT2globalT[d.ID + d.N]) {
            if (d.N == "L") {
              document.getElementById("lickSound").play();
            } else if (d.N == "S") {
              document.getElementById("rewardSound").play();
            }
          }
          delete deltaT2globalT[d.ID + d.N];
        }
      });
    }
  }

  $: if (DOMRect) {
    width = DOMRect.width;
  }

  $: xScale = scaleLinear()
    .domain([$PortentaStreamerTRange.max, $PortentaStreamerTRange.min])
    .range([xLeftOffsetPx, width - xRightOffsetPx]);

  $: yScale = scaleLinear()
    .domain([minYData, maxYData])
    .range([height - yBottomOffsetPx, yTopOffsetPx]);

  $: xTicks = xScale.ticks(5).map((tick) => {
    const readableTime = new Date(tick / 1000).toLocaleTimeString();
    return { value: readableTime, position: xScale(tick) };
  });

  $: yTicks = yScale
    .ticks(nYTicks)
    .map((tick, i) => ({
      value: yTickLabels == null ? tick : yTickLabels[i],
      position: yScale(tick),
    }));
</script>

<div class="portenta-stream-card">
  <audio id="rewardSound" src="assets/rewardsound.mp3" preload="auto"
  ></audio>
  <audio id="lickSound" src="assets/clicklick.mp3" preload="auto"></audio>
  <!-- <audio id="lickSound" src="src/assets/licklick.mp3" preload="auto"></audio> -->

  <div id="card-header-div">
    <div id="label-headers-div">
      <h1>{title}</h1>
    </div>
    {#if isActive}
      <!-- add three toggle boxes here -->
      {#if wsEndpointName === "ballvelocity"}
        <div id="toggle-boxes-div">
          <input
            type="checkbox"
            bind:checked={showForward}
            title="Show forward"
          />
          <input
            type="checkbox"
            bind:checked={showSideways}
            title="Show sideways"
          />
          <input
            type="checkbox"
            bind:checked={showRotation}
            title="Show rotation"
          />
        </div>
      {/if}

      <div id="timestamp-headers-div">
        <!-- <h1>{formatTime($store.initiated? $dataStore[$dataStore.length-1].PCT : $globalT)}</h1> -->
      </div>
      <div id="timestamp-headers-div">
        <h1>{fromTimestamp ? fromTimestamp : ""}</h1>
        <h1>{toTimestamp ? toTimestamp : ""}</h1>
        <!-- <h1>{formatTime($store.initiated? $dataStore[$dataStore.length-1].PCT : $globalT)}</h1> -->
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
    class="plot-div"
    bind:contentRect={DOMRect}
    style="height: {isActive ? height : 0}px"
  >
    {#if isActive}
      <svg {width} {height} overflow="visible">
        <g>
          {#each $dataStore as point, i}
            {#if wsEndpointName === "ballvelocity"}
              {#if showRotation}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(point.pitch)}
                  r="2"
                  stroke="var(--fg-color)"
                  stroke-width="1.5"
                  fill="none"
                />
              {/if}
              {#if showForward}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(point.raw)}
                  r="3"
                  fill="var(--fg-color)"
                />
              {/if}
              {#if showSideways}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(point.yaw)}
                  r="3"
                  fill="#888888"
                />
              {/if}
              <!-- fresh package or not -->
              {#if point.F == 0 && (showForward || showSideways || showRotation)}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(maxYData)}
                  r="3"
                  fill="var(--error-color)"
                />
              {/if}
            {/if}

            {#if wsEndpointName === "portentaoutput"}
              {#if point.N === "L"}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(1)}
                  r="3"
                  fill="var(--fg-color)"
                />
                <line
                  x1={xScale(point.PCT)}
                  y1={yScale(1)}
                  x2={xScale(point.PCT + point.V)}
                  y2={yScale(1)}
                  stroke="var(--fg-color)"
                  stroke-width="2"
                />
              {/if}
              {#if point.N === "R"}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(2)}
                  r="3"
                  fill="var(--fg-color)"
                />
                <line
                  x1={xScale(point.PCT)}
                  y1={yScale(2)}
                  x2={xScale(point.PCT + point.V * 1000)}
                  y2={yScale(2)}
                  stroke="var(--fg-color)"
                  stroke-width="2"
                />
              {/if}
              {#if point.N === "S"}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(3)}
                  r="3"
                  fill="var(--good-color)"
                />
                <line
                  x1={xScale(point.PCT)}
                  y1={yScale(3)}
                  x2={xScale(point.PCT + point.V * 1000)}
                  y2={yScale(3)}
                  stroke="var(--good-color)"
                  stroke-width="2"
                />
              {/if}

              {#if point.N === "F"}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(3)}
                  r="3"
                  fill="var(--error-color)"
                />
                <line
                  x1={xScale(point.PCT)}
                  y1={yScale(3)}
                  x2={xScale(point.PCT + point.V * 1000)}
                  y2={yScale(3)}
                  stroke="var(--error-color)"
                  stroke-width="2"
                />
              {/if}
              {#if point.N === "A"}
                <circle
                  cx={xScale(point.PCT)}
                  cy={yScale(4)}
                  r="3"
                  fill="var(--fg-color)"
                />
              {/if}
            {/if}
          {/each}
        </g>

        {#if $store.initiatedInspect}
          <defs>
            <marker
              id="arrowheadTimelinePS"
              markerWidth="4.6875"
              markerHeight="3.28125"
              refX="-1.25"
              refY="1.640625"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path
                d="M0,0 L0,3.28125 L4.6875,1.640625 z"
                fill="var(--fg-color)"
              />
            </marker>
          </defs>

          <line
            id="timeline-cursor"
            x1={xScale($globalT)}
            y1={yScale(maxYData) - 25}
            x2={xScale($globalT)}
            y2={yScale(minYData) - 2}
            stroke="var(--fg-color)"
            stroke-width="3"
            marker-start="url(#arrowheadTimelinePS)"
          />
        {/if}

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
            text-anchor="middle">{value}</text
          >
        {/each}

        <!-- x label background box: [s] -->
        <rect
          x={xLeftOffsetPx - yAxisOffsetPx - 22}
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

  #timestamp-headers-div {
    flex-grow: 12;
    display: flex;
    justify-content: flex-end;
  }

  #timestamp-headers-div h1 {
    font-size: 12pt;
    margin: 1em;
    font-family: "Courier New", Courier, monospace;
    color: var(--fg-color);
  }

  #toggle-boxes-div {
    display: flex;
    justify-content: flex-start;
    gap: 10px;
    margin-left: 1em;
  }

  #toggle-boxes-div input[type="checkbox"] {
    width: 20px; /* Increase checkbox size */
    height: 20px; /* Increase checkbox size */
    margin-right: 5px;
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
  #label-headers-div h1 {
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
