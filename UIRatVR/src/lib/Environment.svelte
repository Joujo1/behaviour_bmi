<script>
  import {
    store,
    unityData,
    unityTrialData,
    portentaData,
  } from "../../store/stores";
  import { unityWSOnMessageCallback, setupUnityWS } from "../unityoutputWS.js";
  import {
    trialUnityVelData,
    trialPortentaEventData,
  } from "../../store/stores.js";

  import { select, drag, line, easeBounce, scaleLinear } from "d3";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { GETParadigmsEnvironement } from "../monitor_api.js";
  import { GETSelectedParadigm } from "../monitor_api.js";
  import { writable } from "svelte/store";

  // websocket
  let closeCallback = (msg) => {
    "Calling empty closeCallback";
  };

  // reactive elements (circles is a d3.selection)
  let svg;
  let circles;

  // visual properties
  let isActive = false;
  let title = "Environment";
  let width = 100; // intial value, DOMRect will be determined dynamically
  let trialVelPlotHeight = 60; //constant
  let trialPortentaEventPlotHeight = 20; //constant
  let unityEnvPlotHeight = 200; //should be dynamic for each paradigm evv size
  let height =
    trialPortentaEventPlotHeight + trialVelPlotHeight + unityEnvPlotHeight + 10;
  let DOMRect = { width: width };

  let xScaleZPosition;
  let fromZPosition = 0;
  let toZPosition = 0;
  let yScaleYPosition;
  let fromYPosition = 0;
  let toYPosition = 0;

  let yScaleVelocity;
  let fromVelocity = 0;
  let toVelocity = 0;
  let vel_threshold = 0.3;

  $: if (DOMRect) {
    width = DOMRect.width;
  }
  let paradigm_env;
  let paradigm_name = "";
  let paradigm_id;

  async function switchCardOnOff(event) {
    if (!isActive) {
      paradigm_name = await GETSelectedParadigm();
      console.log("paradigm_name", paradigm_name);
      if (typeof paradigm_name === "string") {
        //sucess
        paradigm_id = parseInt(paradigm_name.slice(1, 5));
        console.log(paradigm_id, paradigm_name);
      }

      // error handling, no string but object returned
      if (typeof paradigm_name === "object") {
        $store.showModal = true;
        $store.modalMessage = paradigm_name.detail;
        return;
      } else if (![200, 800, 1100].includes(paradigm_id)) {
        $store.showModal = true;
        $store.modalMessage = `${paradigm_name} is not supported`;
        return;
      } else {
        paradigm_env = await GETParadigmsEnvironement();
        isActive = !isActive;
        // height = 230;
        closeCallback = setupUnityWS($store.initiated);

        // if (paradigm_id === 800) {
        //   paradigm_env.envX_size /= 4;
        //   width = 140;
        //   height = 140;
        // }
        console.log("paradigm_env", paradigm_env);

        if (paradigm_env) {
          fromZPosition = -paradigm_env.envY_size / 2;
          toZPosition = paradigm_env.envX_size / 2;
          fromYPosition = paradigm_env.envY_size / 2;
          toYPosition = paradigm_env.envY_size / -2;
          fromVelocity = 0;
          toVelocity = 40;
        }

        // transform from topleft being 0,0 in excel to to center being 0,0 in unity
        Object.values(paradigm_env.pillars).forEach((pillar) => {
          pillar.y -= paradigm_env.envY_size / 2;
          pillar.y *= -1;
          pillar.x -= paradigm_env.envX_size / 2;
          pillar.x *= -1;
        });

        // sort pillars by id
        // Sort pillars by id
        const sortedPillars = Object.values(paradigm_env.pillars).sort(
          (a, b) => a.id - b.id
        );

        // Convert sorted array back to object if necessary
        paradigm_env.pillars = sortedPillars.reduce((acc, pillar, index) => {
          acc[index] = pillar;
          return acc;
        }, {});

        console.log("paradigm_env", paradigm_env);

        if ([800, 1100].includes(paradigm_id)) {
          fromYPosition = -12;
          toYPosition = 35;
        }
      }
    } else {
      isActive = !isActive;
      closeCallback();
    }
  }

  $: xScaleZPosition = scaleLinear()
    .domain([fromZPosition, toZPosition])
    .range([10, width - 10]);

  $: yScaleYPosition = scaleLinear()
    .domain([fromYPosition, toYPosition])
    .range([70, unityEnvPlotHeight - 10]);

  $: yScaleVelocity = scaleLinear()
    .domain([fromVelocity, toVelocity])
    .range([trialVelPlotHeight - 10, 10]);

  // $: xTicks = xScaleZPosition.ticks(5).map((tick) => {
  //   const readableTime = new Date(tick / 1000).toLocaleTimeString();
  //   return { value: readableTime, cur_position: xScale(tick) };
  // });

  // $: yTicks = yScale
  //   .ticks(nYTicks)
  //   .map((tick, i) => ({
  //     value: yTickLabels == null ? tick : yTickLabels[i],
  //     cur_position: yScale(tick),
  //   }));
</script>

<div class="portenta-stream-card">
  <div id="card-header-div">
    <div>
      <h1>{title} {paradigm_name}</h1>
    </div>
    <div>
      <input
        id="sum-threshold-number"
        type="number"
        bind:value={vel_threshold}
        title="color threshold"
      />
    </div>
    <div id="swtich-btn-div">
      <ShowHideCardButton
        onClickCallback={switchCardOnOff}
        showCross={isActive}
      />
    </div>
  </div>
  <div
    class="environmet-div"
    bind:contentRect={DOMRect}
    style="height: {isActive ? height : 0}px"
  >
    {#if isActive && paradigm_env}
      <!-- VELOCITY PLOT -->
      <svg id="trial-velocity-plot" {width} height={trialVelPlotHeight}>
        {#each $trialUnityVelData as trialVelocityValue}
          <!-- {console.log("trialVelocityValue", trialVelocityValue)} -->
          <circle
            cx={xScaleZPosition(trialVelocityValue.cur_position)}
            cy={yScaleVelocity(trialVelocityValue.frameVelocity)}
            r="1.5"
            fill={trialVelocityValue.frameVelocity > vel_threshold
              ? "var(--fg-color)"
              : "var(--good-color)"}
          />
        {/each}
        <line
          x1="0"
          y1={yScaleVelocity(vel_threshold)}
          x2={width}
          y2={yScaleVelocity(vel_threshold)}
          stroke="var(--fgFaint-color)"
          stroke-width="1"
        />
      </svg>

      <!-- PORTENTA EVENT PLOT -->
      <svg
        id="trial-portenta-event-plot"
        {width}
        height={trialPortentaEventPlotHeight}
      >
        {#each $trialPortentaEventData as point}
          <!-- {console.log("i", i)} -->

          {#if point.N === "L"}
            <circle
              cx={xScaleZPosition(point.cur_position)}
              cy={10}
              r="1"
              fill="var(--fg-color)"
            />
          {:else if point.N === "R"}
            <circle
              cx={xScaleZPosition(point.cur_position)}
              cy={3}
              r="4"
              fill="var(--good-color)"
            />
          {:else if point.N === "V"}
            <circle
              cx={xScaleZPosition(point.cur_position)}
              cy={3}
              r="4"
              fill="var(--error-color)"
            />
          {/if}
        {/each}
      </svg>

      <svg id="unity-env-plot" {width} height={unityEnvPlotHeight}>
        <rect
          style="fill:var(--bgFaint-color);fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.10644;stroke-linecap:round;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1"
          id="background"
          {width}
          height={unityEnvPlotHeight}
        ></rect>

        {#each Object.values(paradigm_env.pillars) as pillar}
          {#if [800, 1100].includes(paradigm_id)}
            {#if pillar.id != 0}
              {console.log(pillar)}
            {/if}

            {#if paradigm_env.pillar_details[pillar.id].pillarRewardRadius}
              <!-- reward pillars -->
              <circle
                class="pillar_{pillar.id}"
                cx={xScaleZPosition(pillar.y)}
                cy={yScaleYPosition(pillar.x)}
                r={paradigm_env.pillar_details[pillar.id].pillarRewardRadius *
                  2}
                fill="var(--fg-color)"
                opacity={0.5}
              >
              <title>PillarID:{pillar.id}:Reward, X={pillar.y}</title>
              </circle>

              <circle
                class="pillar_{pillar.id}"
                cx={xScaleZPosition(pillar.y)}
                cy={yScaleYPosition(pillar.x)}
                r={paradigm_env.pillar_details[pillar.id].pillarRewardRadius *
                  2}
                stroke="var(--accent-color)"
                stroke-width="3"
                fill="none"
              >
              <title>PillarID:{pillar.id}:Reward, X={pillar.y}</title>
              </circle>
            {:else}
              <!-- other pillars -->
              <circle
                class="pillar_{pillar.id}"
                cx={xScaleZPosition(pillar.y)}
                cy={yScaleYPosition(pillar.x)}
                r={paradigm_env.pillar_details[pillar.id].pillarRadius * 2}
                opacity={Math.max(
                  0.15,
                  paradigm_env.pillar_details[pillar.id].pillarTransparency
                )}
                stroke="var(--fg-color)"
                fill={paradigm_env.pillar_details[pillar.id].pillarTexture !=
                "black"
                  ? "var(--accent-color)"
                  : "none"}
              >
              <title>PillarID:{pillar.id}, X={pillar.y}</title>
            </circle>
            {/if}
          {/if}
        {/each}

        <!-- rat postition -->
        {#each $unityData as unityFrame, i}
          {#if unityFrame.N === "U"}
            <circle
              id="unityFrame"
              cx={xScaleZPosition(unityFrame.Z)}
              cy={yScaleYPosition(unityFrame.X)}
              r="4"
              fill-opacity={(i * 1) / $unityData.length}
              fill="var(--fg-color)"
            >
            <title>UnityFrame: {i}, X={unityFrame.Z}</title>
            </circle>
          {/if}
        {/each}

        <path
          id="vertical-path"
          style="stroke:var(--fg-color);stroke-opacity:.1;stroke-width:0.4;stroke-linecap:round;stroke-dasharray:none;stroke-dashoffset:0;"
          d="M 0,0 V {unityEnvPlotHeight}"
        />

        <path
          id="horizontal-path"
          style="stroke:#ffffff;stroke-width:0.409;stroke-linecap:round;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:.2"
          d="M 0,0 H {width}"
        />
        <!-- GRID -->
        <g>
          {#each Array.from({ length: Math.ceil(paradigm_env.envX_size / 10) + 1 }, (_, i) => -paradigm_env.envX_size / 2 + i * 10) as vLineXPos}
            <use
              href="#vertical-path"
              transform="translate({xScaleZPosition(vLineXPos)}, 0)"
            />
          {/each}

          {#each Array.from({ length: Math.ceil(paradigm_env.envY_size / 10) + 1 }, (_, i) => -paradigm_env.envY_size / 2 + i * 10) as hLineYPos}
            <use
              href="#horizontal-path"
              transform="translate(0, {yScaleYPosition(hLineYPos)})"
            />
          {/each}
        </g>
      </svg>
    {/if}
  </div>
</div>

<style>
  .environmet-div {
    transition: height 0.2s ease-in-out;
    margin-top: 5px;
  }
  .portenta-stream-card {
    border: 1px solid var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    flex-grow: 1;
    max-width: 680px;
    min-width: 300px;
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

  #sum-threshold-number {
    width: 20px;
    height: 20px;
    margin-left: 1em;
    -moz-appearance: textfield;
  }
</style>
