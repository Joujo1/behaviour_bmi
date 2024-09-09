<script>
  import { line, min, max } from "d3";
  import { scaleLinear } from "d3";
  import { store, globalT } from "../../store/stores.js";
  import { time2str } from "../monitor_api.js";
  import {
    GETTrials,
    GETEvents,
    GETForwardVelocity,
    GETUnityFrames,
  } from "../inspect_api.js";
  import { get } from "svelte/store";
  import { afterUpdate } from "svelte";

  let trials = [];
  let events = [];
  let velocities = {};

  const maxCMPerSecond = 100;

  let trialsTmin;
  let trialsTmax;
  let initiatedInspectState = false;
  let timestamp;

  let trialsIDmin;
  let trialsIDmax;
  let trialsIDminSelected;
  let trialsIDmaxSelected;

  let xTicks = [];
  let yScaleVelocity;
  let staytimeYScale;

  let width = 0;
  let height = 220;
  let DOMRect = { width: width };
  let isPlaying = false;

  const waitTimePlotHeight = 40;
  const lickPlotHeight = 20;
  const velocitiesPlotHeight = 60;
  const trialsHeight = 30;

  function getOutcomeColor(outcome) {
    if (outcome >= 0 && outcome <= 5) {
      return "var(--outcome-" + outcome + "-color)";
    } else {
      return "var(--fg-color)";
    }
  }

  function handleClick(event, trial) {
    console.log("Trial clicked:", trial);
    $globalT = trial.SPCT;
  }

  function handleKeydown(event, trial) {
    if (event.key === "Enter" || event.key === " ") {
      handleClick(event, trial);
    }
  }

  function togglePlay() {
    isPlaying = !isPlaying;
  }

  async function getTrials() {
    trials = await GETTrials();
    initTrialVariables();
  }

  async function getEvents() {
    events = await GETEvents();
    console.log(events);
  }

  async function getForwardVelocities() {
    velocities = await GETForwardVelocity();
    console.log("velocities", velocities);
  }

  function initTrialVariables() {
    $globalT = trials[0].SPCT;
    const startTimestamps = trials
      .map((trial) => trial.SPCT)
      .filter((ts) => ts !== null);
    const endTimestamps = trials
      .map((trial) => trial.EPCT)
      .filter((ts) => ts !== null);
    trialsTmin = Math.min(...startTimestamps);
    trialsTmax = Math.max(...endTimestamps);
    trialsIDmin = trials[0].ID;
    trialsIDmax = trials[trials.length - 1].ID;
    // init the selected trials input field
    trialsIDminSelected = trialsIDmin;
    trialsIDmaxSelected = trialsIDmax;
    console.log("trialsTmin:", trialsTmin, "trialsIDmin:", trialsIDmin);
    console.log("trialsTmax:", trialsTmax, "trialsIDmax:", trialsIDmax);
  }

  $: if (initiatedInspectState != $store.initiatedInspect) {
    if ($store.initiatedInspect) {
      getTrials();
      getEvents();
      getForwardVelocities();
      initiatedInspectState = true;
    } else {
      initiatedInspectState = false;
      trials = [];
      events = [];
      velocities = {};
      timestamp = "";
    }
  }

  $: if (trials.length) {
    const from = trials.find((trial) => trial.ID === trialsIDminSelected).SPCT;
    const to = trials.find((trial) => trial.ID === trialsIDmaxSelected).EPCT;
    xScale = scaleLinear().domain([from, to]).range([0, width]);

    if ($globalT < from) {
      $globalT = from;
    } else if ($globalT > to) {
      $globalT = trials.find((trial) => trial.ID === trialsIDmaxSelected).SPCT;
    }
  }

  $: if (DOMRect) {
    width = DOMRect.width;
  }

  $: xScale = scaleLinear().domain([trialsTmin, trialsTmax]).range([0, width]);

  $: if (Object.values(velocities).length) {
    console.log("velocities", velocities);
    yScaleVelocity = scaleLinear()
      .domain([0, maxCMPerSecond])
      .range([velocitiesPlotHeight, 0]);
  }

  $: if (trials.length) {
    staytimeYScale = scaleLinear()
      .domain([0, 6])
      .range([waitTimePlotHeight - waitTimePlotHeight / 3 - 2, 0]);
  }

  $: if (trialsTmin && trialsTmax) {
    const minutes = Math.floor((trialsTmax - trialsTmin) / 1e6 / 60);
    if (isFinite(minutes)) {
      xTicks = [{ position: xScale(trialsTmax), value: `${minutes}min` }];
    }
  }

  $: if ($globalT) {
    timestamp = time2str($globalT / 1000);
  }

  $: if (trials.length) {
    console.log(trialsIDminSelected, trialsIDmaxSelected);
  }

  // globalT increases here
  let clear;
  $: {
    console.log("isPlaying", ($store.initiatedInspect && isPlaying));

    clearInterval(clear);
    clear = setInterval(() => {
      if ($store.initiatedInspect && isPlaying) {
        updateGlobalT(33333); // 30fps
      }
    }, 33.333);
  }

  let updateGlobalT = (delta) => {
    let newGlobalT = $globalT + delta;
    // general bounds check
    const minT = trials[trialsIDminSelected-1].SPCT;
    const maxT = trials[trialsIDmaxSelected-1].EPCT;
    // wants to go too far back, limit to minT
    if (newGlobalT < minT) {
      console.log("newGlobalT < minT");
      newGlobalT = minT;
    // wants to go too far into the future, limit to maxT
    } else if (newGlobalT > maxT) {
      console.log("newGlobalT > maxT");
      newGlobalT = maxT;
      if (isPlaying) {
        isPlaying = false;
      }
    }

    $globalT = newGlobalT;
  };

  // $:console.log("globalT", $globalT);

</script>

<div
  id="session-timeline-div"
  bind:contentRect={DOMRect}
  style="height: {true ? height : 0}px"
>
  <div id="waitTimePlot">
    {#if trials}
      <svg {width} height={waitTimePlotHeight} overflow="visible">
        {#each trials as trial}
          {#if trial.ID >= trialsIDminSelected && trial.ID <= trialsIDmaxSelected}
            <rect
              x={xScale(trial.SPCT)}
              y={(waitTimePlotHeight * 2) / 3}
              height={10}
              width={xScale(trial.EPCT) - xScale(trial.SPCT)}
              fill={trial.cue == 1 ? "var(--fg-color)" : "var(--fgFaint-color)"}
              stroke="1px solid var(--fg-color)"
            />
            <!-- <line
            x1={xScale(trial.PCT_enter_cue2)}
            y1={staytimeYScale(0)}
            x2={xScale(trial.PCT_enter_cue2)}
            y2={staytimeYScale(trial.staytime_cue2/1e6)}
            stroke="var(--fg-color)"
            stroke-width=".5"
          /> -->
            <line
              x1={xScale(trial.PCT_enter_r1)}
              y1={staytimeYScale(0)}
              x2={xScale(trial.PCT_enter_r1)}
              y2={staytimeYScale(trial.staytime_r1 / 1e6)}
              stroke={"var(--fg-color)"}
              stroke-width="2"
            />
            <line
              x1={xScale(trial.PCT_enter_r2)}
              y1={staytimeYScale(0)}
              x2={xScale(trial.PCT_enter_r2)}
              y2={staytimeYScale(trial.staytime_r2 / 1e6)}
              stroke={"var(--fgFaint-color)"}
              stroke-width="2"
            />
          {/if}
        {/each}
      </svg>
    {/if}
  </div>

  <div id="lickPlot">
    {#if events}
      <svg {width} height={lickPlotHeight} overflow="invisible">
        {#each events as event}
          {#if event.N === "L"}
            <circle
              cx={xScale(event.PCT)}
              cy={lickPlotHeight / 2}
              r="2"
              fill="var(--fg-color)"
            />
          {/if}
          {#if event.N === "R"}
            <line
              x1={xScale(event.PCT)}
              y1={0}
              x2={xScale(event.PCT)}
              y2={lickPlotHeight}
              stroke="var(--good-color)"
              stroke-width="2"
            />
          {/if}
        {/each}
      </svg>
    {/if}
  </div>

  <div id="velocityPlot">
    {#if Object.values(velocities).length}
      <svg {width} height={velocitiesPlotHeight} overflow="invisible">
        <g>
          {#each Object.entries(velocities) as [pct, vel]}
            <circle
              cx={xScale(pct*1e6)}
              cy={yScaleVelocity(vel)}
              r="1"
              fill="var(--fg-color)"
            />
          {/each}
        </g>
      </svg>
    {/if}
  </div>

  <div id="trialTimeline">
    {#if trials}
      <svg {width} height={trialsHeight} overflow="visible">
        {#each trials as trial}
          {#if trial.ID >= trialsIDminSelected && trial.ID <= trialsIDmaxSelected}
            <rect
              x={xScale(trial.SPCT)}
              y={0}
              height={trialsHeight}
              width={xScale(trial.EPCT) - xScale(trial.SPCT)}
              fill={getOutcomeColor(trial.O)}
              stroke="1px solid var(--fg-color)"
              on:click={(event) => handleClick(event, trial)}
              on:keydown={(event) => handleKeydown(event, trial)}
              tabindex="0"
              role="button"
            />
          {/if}
        {/each}
        <defs>
          <marker
            id="arrowheadTimeline"
            markerWidth="4.6875"
            markerHeight="3.28125"
            refX="-83"
            refY="1.640625"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path
              d="M0,0 L0,3.28125 L4.6875,1.640625 z"
              fill="var(--fg-color)"
              transform="rotate(180 2.34375 1.640625)"
            />
          </marker>
        </defs>

        <line
          x1={xScale($globalT)}
          y1={-height + 80}
          x2={xScale($globalT)}
          y2={trialsHeight }
          stroke="var(--fg-color)"
          stroke-width="2"
          marker-start="url(#arrowheadTimeline)"
          visibility={trials.length ? "visible" : "hidden"}
        />
        {#each xTicks as { value, position }}
          <text
            x={position}
            y={trialsHeight + 16}
            fill="var(--fg-color)"
            font-size="10pt"
            text-anchor="middle">{value}</text
          >
        {/each}
      </svg>
    {/if}
  </div>

  <div id="timeline-controls">
    <div id="trial-subset-selector">
      <p>Trial</p>
      {#if trials.length}
        <input
          type="number"
          min={trialsIDmin}
          max={Math.min(trialsIDmaxSelected - 1, trialsIDmax - 1)}
          bind:value={trialsIDminSelected}
        />
      {/if}
      <p>-</p>
      {#if trials.length}
        <input
          type="number"
          min={Math.max(trialsIDminSelected + 1, trialsIDmin + 1)}
          max={trialsIDmax}
          bind:value={trialsIDmaxSelected}
        />
      {/if}
    </div>
    <div id="timeline-control-buttons">
      <button
        id="timeline-prev-btn"
        class="timeline-control-button"
        style="color: var(--fg-color);"
        on:click={() => updateGlobalT(-3 * 1e6)}
      >
        <svg>
          <line
            x1="18"
            y1="6"
            x2="12"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
          <line
            x1="18"
            y1="18"
            x2="12"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
          <line
            x1="10"
            y1="6"
            x2="4"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
          <line
            x1="10"
            y1="18"
            x2="4"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
        </svg>
      </button>

      <button
        id="timeline-play-btn"
        class="timeline-control-button"
        style="color: var(--fg-color);"
        on:click={togglePlay}
      >
        {#if isPlaying}
          <svg viewBox="0 0 24 24">
            <line
              x1="6"
              y1="6"
              x2="6"
              y2="18"
              stroke="var(--fg-color)"
              stroke-width="4"
            />
            <line
              x1="14"
              y1="6"
              x2="14"
              y2="18"
              stroke="var(--fg-color)"
              stroke-width="4"
            />
          </svg>
        {:else}
          <svg viewBox="0 0 24 24">
            <polygon points="6,4 20,12 6,20" fill="currentColor" />
          </svg>
        {/if}
      </button>
      <button
        id="timeline-next-btn"
        class="timeline-control-button"
        style="color: var(--fg-color); padding: 0; margin: 0; width: 24px; height: 24px;"
        on:click={() => updateGlobalT(3 * 1e6)}
      >
        <svg>
          <line
            x1="12"
            y1="6"
            x2="18"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
          <line
            x1="12"
            y1="18"
            x2="18"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
          <line
            x1="4"
            y1="6"
            x2="10"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
          <line
            x1="4"
            y1="18"
            x2="10"
            y2="12"
            stroke="var(--fg-color)"
            stroke-width="2"
          />
        </svg>
      </button>
    </div>
    <div id="timestamp-headers-div">
      {#if timestamp}
        <h1>{timestamp}</h1>
      {/if}
    </div>
  </div>
</div>

<style>
  #timestamp-headers-div h1 {
    font-size: 12pt;
    margin-right: 2em;
    font-family: "Courier New", Courier, monospace;
    color: var(--fg-color);
  }
  #session-timeline-div {
    flex: 1;
    margin-left: 40px;
    margin-right: 30px;
  }

  #trialTimeline {
    flex: 1;
  }

  #trialTimeline rect:hover {
    stroke: var(--bgFaint-color);
    stroke-width: 1px;
    cursor: pointer;
  }

  #trialTimeline line {
    transition: all 0.1s ease-in-out;
    stroke-linecap: round;
  }

  #timeline-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 30px;
  }
  #timeline-control-buttons {
  }

  #trial-subset-selector {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  #trial-subset-selector input {
    width: 40px;
    height: 20px;
    border-radius: 5px;
    text-align: center;
    box-shadow: none;
    border: 1px solid var(--bgFaint-color);
  }

  .timeline-control-button {
    background: none;
    border: none;
    cursor: pointer;
  }

  .timeline-control-button svg {
    width: 24px;
    height: 24px;
  }
</style>
