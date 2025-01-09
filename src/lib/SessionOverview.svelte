<script>
  import { store, unityData, unityTrialData } from "../../store/stores";
  import { openWebsocket, GETSessionStartTime } from "../monitor_api.js";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { setupUnityWS } from "../unityoutputWS.js";

  import { unityStreamerTRange } from "../../store/stores";
  import { scaleLinear } from "d3";

  let minYData = 0;
  let maxYData = 0;
  let minXData = 0;
  let maxXData = 0;
  export let height = 200;
  export let title = "Session Overview";

  export let nYTicks = 3;
  export let yTickLabels = null;
  export let yTopOffsetPx = 20;
  export let xLeftOffsetPx = 70;

  let isActive = false;
  let closeCallback = () => {};
  let secondCloseCallback = () => {};
  let width = 0;
  let DOMRect = { width: width };

  let paradigmRunningState = false;

  let fps = 0.0;
  let sessionStartTime = 0;
  let currentTime = 0;
  let rewardsN = 0;
  let rewardsMl = 0;
  let sessionDuration = 0;
  let sessionDurationStr = "00:00";

  let lastTrial = {};
  let sizeScaler = 5;

  const tickLength = 8;
  const xRightOffsetPx = 20;
  const yBottomOffsetPx = 50;
  const yAxisOffsetPx = 20;

  $: if (DOMRect) {
    width = DOMRect.width;
  }

  $: xScale = scaleLinear()
    .domain([minXData, maxXData])
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
    .map((tick, i) => ({
      value: yTickLabels == null ? tick : yTickLabels[i],
      position: yScale(tick),
    }));

  
  $: if (lastTrial && $unityTrialData.length && $unityTrialData[$unityTrialData.length - 1].ID != lastTrial.ID) {
    lastTrial = $unityTrialData[$unityTrialData.length - 1];
    console.log("Unity Trial Data: ", $unityTrialData[$unityTrialData.length - 1], lastTrial);
    sizeScaler = 20 / Math.sqrt($unityTrialData.length)

    if (lastTrial.C && lastTrial.C == 2) {
      console.log("Correct trial detected");
    }



  }

  // $: console.log($unityData);
  // $: console.log($unityData.length);

  $: if ($unityData.length > 10) {
    // Calculate FPS
    const cur_t = Math.floor($unityData[$unityData.length - 1].PCT / 1e3);
    const prv_t = Math.floor($unityData[$unityData.length - 2].PCT / 1e3);
    fps = cur_t - prv_t;
    // Calculate session duration
    sessionDuration = calculateTimeDelta();
    sessionDurationStr =
      "Session duration: " +
      Math.floor(sessionDuration / 60)
        .toString()
        .padStart(2, "0") +
      ":" +
      (sessionDuration % 60).toString().padStart(2, "0") +
      " min";

    // Calculate reward
    $unityData.filter((data) => data.S % 100 == 1);
  }

  $: if ($unityTrialData.length > 0) {
    minXData = Math.min(...$unityTrialData.map((trial) => trial.ID)) - 2;
    maxXData = Math.max(...$unityTrialData.map((trial) => trial.ID)) + 2;

    // console.log($unityTrialData);
    maxYData = Math.max(...$unityTrialData.map((trial) => trial.TD)) / 1e6;
  }

  // Function to calculate the delta
  function calculateTimeDelta() {
    const currentTime = Math.floor(Date.now() / 1000); // Current time in Unix timestamp (seconds)
    const delta = currentTime - sessionStartTime; // Delta in seconds
    return delta;
  }

  async function switchCardOnOff(event) {
    if (!isActive) {
      const strTime = await GETSessionStartTime();
      // Convert to Date object and then to Unix timestamp (in seconds)
      sessionStartTime = Math.floor(new Date(strTime).getTime() / 1000);

      console.log("Session Start Time: ", sessionStartTime);
      isActive = !isActive;
      console.log("setting up unity ws from session Overview");
      closeCallback = setupUnityWS();

      secondCloseCallback = openWebsocket("portentainput", updateRewardCounter);
    } else {
      isActive = !isActive;
      closeCallback();
      secondCloseCallback();
    }
  }

  let valveOpenTime = 20;
  async function updateRewardCounter(msg) {
    const cmd = JSON.parse(msg.data).split("\r\n")[0];
    const [firstChar, ...rest] = cmd;
    const values = rest.join("");
    if (firstChar == "S") {
      const rewards = values.split(",");
      valveOpenTime = parseFloat(rewards[0]);
      rewardsMl += (valveOpenTime*0.295 -10) / 1000;
      rewardsMl = parseFloat(rewardsMl.toFixed(3));

      rewardsN += 1;
    } else if (firstChar == "V") {
      console.log("Subtracting last reward open valve time ", valveOpenTime);
      rewardsMl -= (valveOpenTime*0.295 -10) / 1000;
      rewardsMl = parseFloat(rewardsMl.toFixed(3));

    }
  }

  $: if (paradigmRunningState !== undefined && $store.paradigmRunning &&
         paradigmRunningState != $store.paradigmRunning) {
    console.log("paradigmRunningState != $store.paradigmRunning", paradigmRunningState, $store.paradigmRunning)
    console.log("Paradigm Running State Changed");
    if (isActive) {
      switchCardOnOff();
      switchCardOnOff();
    } else {
      switchCardOnOff();
    }
    paradigmRunningState = $store.paradigmRunning;
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
        disabled={!$store.initiated}
        
      />
    </div>
  </div>
  <div
    class="plot-div"
    bind:contentRect={DOMRect}
    style="height: {isActive ? height : 0}px"
  >
    {#if isActive}
      <div id="session-overview-infos-div">
        <p>Rewards: {rewardsN}, {rewardsMl} ml</p>
        <p>{sessionDurationStr}</p>
        <p>FPS: {fps}</p>
      </div>

      <svg {width} {height} overflow="visible">
        {#each $unityTrialData as trialObj, i}
          {#if (trialObj.C==undefined || trialObj.C == 1 || trialObj.DR == 1)}
            <circle
              cx={xScale(trialObj.ID)}
              cy={yScale(trialObj.TD / 1e6)}
              r={trialObj.DR && trialObj.DR==1 ? (trialObj.O%10)+1 *sizeScaler :
                 (trialObj.O + 1) *  (sizeScaler)}
              fill={trialObj.O > 0
                ? "var(--good-color)"
                : "var(--error-color)"}
            />
          {/if}
          {#if ((trialObj.C && trialObj.C == 2) || trialObj.DR == 1) }
            <rect
              x={xScale(trialObj.ID) - 10}
              y={yScale(trialObj.TD / 1e6) - 10}
              width={trialObj.DR && trialObj.DR==1 ? (Math.floor(trialObj.O/10))+1 *2*sizeScaler :
                     (trialObj.O + 1) *  2*(sizeScaler)}
              height={trialObj.DR && trialObj.DR==1 ? (Math.floor(trialObj.O/10))+1 *2*sizeScaler :
                     (trialObj.O + 1) *  2*(sizeScaler)}
              fill={trialObj.O > 0
                ? "var(--good-color)"
                : "var(--error-color)"}
              stroke="var(--bg-color)"
              stroke-width="1"
            />
            {/if}
          <title>{JSON.stringify(trialObj)}</title>
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
            text-anchor="middle">{value}</text
          >
        {/each}
        
        <!-- x label background box: [s] -->
        <rect
          id="x-label-background"
          x={xLeftOffsetPx - yAxisOffsetPx - 20}
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
          {"ID"}</text
        >

        <!-- Y Axis -->
        <!-- Y label: [a.u.] -->
        <text
          x={xLeftOffsetPx - tickLength - yAxisOffsetPx + 35}
          y={yTopOffsetPx + 17}
          font-size={18}
          text-anchor="end"
          fill="var(--fg-color)"
          dominant-baseline="middle"
        >
          {"[s]"}</text
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
  #session-overview-infos-div {
    display: flex;
    justify-content: space-between;
    align-items: flex-start; /* Align items at the top */
    margin-top: 0px;
    padding-top: 0px;
    height: 30px;
  }

  #session-overview-infos-div p {
    margin: 0;
    padding: 0;
    margin-right: 50px;
  }
  #session-overview-infos-div p:last-child {
    margin-left: auto;
  }

  .plot-div {
    transition: height 0.2s ease-in-out;
  }
  .portenta-stream-card {
    border: 1px solid var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    flex-grow: 1;
    max-width: 1200px;
    min-width: 400px;
  }
  #card-header-div {
    border-bottom: 1px solid var(--fgFaint-color);
    padding-bottom: 6px;
    display: flex;
    margin-bottom: 10px;
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
