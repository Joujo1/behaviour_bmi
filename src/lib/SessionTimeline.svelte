<script>
  import { scaleLinear } from "d3";
  import { store, globalT } from "../../store/stores.js";
  import { GETTrials } from "../inspect_api.js";
  import { time2str } from "../monitor_api.js";

  let trials = [];
  let trialsTmin;
  let trialsTmax;
  let initiatedInspectState = false;
  let timestamp;

  let xTicks = [];

  let width = 0;
  let trialsHeight = 30;
  let height = 160;
  let DOMRect = { width: width };
  let isPlaying = false;

  function getOutcomeColor(outcome) {
    if (outcome >= 0 && outcome <= 5) {
      return "var(--outcome-" + outcome + "-color)";
    } else {
      return "var(--fg-color)";
    }
  }

  function handleClick(event, trial) {
    console.log("Trial clicked:", trial);
    $globalT = trial.trial_start_pc_timestamp;
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
    $globalT = trials[0].trial_start_pc_timestamp;
    console.log(trials);
    console.log("globalT ", $globalT);
  }

  $: if (initiatedInspectState != $store.initiatedInspect) {
    if ($store.initiatedInspect) {
      getTrials();
      initiatedInspectState = true;
    } else {
      initiatedInspectState = false;
      trials = [];
    }
  }

  $: if (trials) {
    const startTimestamps = trials
      .map((trial) => trial.trial_start_pc_timestamp)
      .filter((ts) => ts !== null);
    const endTimestamps = trials
      .map((trial) => trial.trial_end_pc_timestamp)
      .filter((ts) => ts !== null);
    trialsTmin = Math.min(...startTimestamps);
    trialsTmax = Math.max(...endTimestamps);
    console.log("trialsTmin:", trialsTmin);
    console.log("trialsTmax:", trialsTmax);
  }

  $: if (DOMRect) {
    width = DOMRect.width;
  }

  $: xScale = scaleLinear().domain([trialsTmin, trialsTmax]).range([0, width]);

  $: if (trialsTmin) {
    xTicks = [];
    const tenMinutesInMicroseconds = 10 * 60 * 1e6;
    for (
      let tick = trialsTmin + tenMinutesInMicroseconds;
      tick <= trialsTmax;
      tick += tenMinutesInMicroseconds
    ) {
      xTicks.push({
        value: Math.floor((tick - trialsTmin) / 1e6 / 60) + "min",
        position: xScale(tick),
      });
    }
  }

  $: if ($globalT) {
    timestamp = time2str($globalT / 1000);
  }

  // globalT increases here
  let clear;
  $: {
    clearInterval(clear);
    clear = setInterval(() => {
      if ($store.initiatedInspect && isPlaying) {
        $globalT += 33333; // 30fps
      }
    }, 33.333);
  }
</script>

<div
  id="session-timeline-div"
  bind:contentRect={DOMRect}
  style="height: {true ? height : 0}px"
>
  <div id="trialPlots1"></div>
  <div id="trialPlots2"></div>
  <div id="trialPlots3"></div>

  <div id="trialTimeline">
    {#if trials}
      <svg {width} height={trialsHeight} overflow="visible">
        {#each trials as trial}
          <rect
            x={xScale(trial.trial_start_pc_timestamp)}
            y={0}
            height={trialsHeight}
            width={xScale(trial.trial_end_pc_timestamp) -
              xScale(trial.trial_start_pc_timestamp)}
            fill={getOutcomeColor(trial.trial_outcome)}
            stroke="1px solid var(--fg-color)"
            on:click={(event) => handleClick(event, trial)}
            on:keydown={(event) => handleKeydown(event, trial)}
            tabindex="0"
            role="button"
          />
        {/each}
        <defs>
          <marker
            id="arrowhead"
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
          x1={xScale($globalT)}
          y1={-10}
          x2={xScale($globalT)}
          y2={trialsHeight + 4}
          stroke="var(--fg-color)"
          stroke-width="3"
          marker-start="url(#arrowhead)"
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
    <div id="timestamp-headers-div">
      {#if timestamp}
        <h1>{timestamp}</h1>
      {/if}
      <!-- <h1>{formatTime($store.initiated? $dataStore[$dataStore.length-1].PCT : $globalT)}</h1> -->
    </div>

    <button
      id="timeline-prev-btn"
      class="timeline-control-button"
      style="color: var(--fg-color);"
      on:click={() => ($globalT -= 2 * 60 * 1e6)}
    >
      Prev
    </button>
    <button
      id="timeline-play-btn"
      class="timeline-control-button"
      style="color: var(--fg-color);"
      on:click={togglePlay}
    >
      {#if isPlaying}
        <svg viewBox="0 0 24 24">
          <rect x="6" y="6" width="12" height="12" fill="currentColor" />
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
      style="color: var(--fg-color);"
      on:click={() => ($globalT += 2 * 60 * 1e6)}
    >
      Next
    </button>
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
    justify-content: center;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
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

  #trialPlots1 {
    width: 100%;
    height: 30px;
  }
  #trialPlots2 {
    width: 100%;
    height: 30px;
  }
  #trialPlots3 {
    width: 100%;
    height: 30px;
  }
</style>
