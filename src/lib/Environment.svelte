<script>
  import { store, unityData } from "../../store/stores";
  import { unityWSOnMessageCallback, setupUnityWS } from "../MonitorHelpers.js";
  import { select, drag, line, easeBounce } from "d3";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { GETParadigmsEnvironement } from "../monitor_api.js";

  // websocket
  let closeCallback = () => {};

  // reactive elements (circles is a d3.selection)
  let svg;
  let circles;

  // visual properties
  let isActive = false;
  let title = "Environment";
  let width = 0;
  let height = 0;
  let DOMRect = { width: width, height: height };

  $: if (DOMRect) {
    width = DOMRect.width;
    height = DOMRect.width;
  }
  let paradigm_env;
    $: console.log($unityData);

  async function switchCardOnOff(event) {
    if (!isActive) {
      paradigm_env = await GETParadigmsEnvironement();
      console.log(paradigm_env);

      // check if data is a string (implecitly means an error message)
      if (typeof paradigm_env === "string") {
        $store.showModal = true;
        $store.modalMessage = paradigm_env;
        return;
      } else {
        isActive = !isActive;
        closeCallback = setupUnityWS();
      }
    } else {
      isActive = !isActive;
      closeCallback();
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
  <div
    class="environmet-div"
    bind:contentRect={DOMRect}
    style="height: {isActive ? height : 0}px"
  >
    {#if isActive}
      <svg
        bind:this={svg}
        {width}
        {height}
        viewBox="0 0 {paradigm_env.envX_size} {paradigm_env.envY_size}"
      >
        <defs id="defs1">
          <marker
            markerWidth="1"
            markerHeight="1"
            refX="0"
            refY="0"
            orient="auto-start-reverse"
            id="marker253"
            viewBox="0 0 0.525 1"
            style="overflow:visible"
            preserveAspectRatio="none"
          >
            <path
              style="fill:context-stroke;stroke-linecap:butt"
              d="M 0,-1 1,0 0,1 -0.05,0 Z"
              transform="scale(0.5)"
              id="path253"
            />
          </marker>
          <marker
            markerWidth="1"
            markerHeight="1"
            refX="0"
            refY="0"
            orient="auto-start-reverse"
            id="CapRibbon1"
            viewBox="0 0 1.05 1"
            style="overflow:visible"
            preserveAspectRatio="none"
          >
            <path
              style="fill:context-stroke;stroke-linecap:butt"
              d="M 0,-1 H 2 L 1,0 2,1 H 0 L -0.1,0 Z"
              transform="scale(0.5)"
              id="path252"
            />
          </marker>
        </defs>

        <g id="layer1">
          <rect
            style="opacity:0.5;fill:var(--bgFaint-color);fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.10644;stroke-linecap:round;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1"
            id="background"
            width={paradigm_env.envX_size}
            height={paradigm_env.envY_size}
          />
          <rect
            style="fill:var(--bgFaint-color);fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.106;stroke-linecap:round;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1"
            id="mainfloor"
            x={paradigm_env.wallzone_size*60}
            y={paradigm_env.wallzone_size*60}
            width={paradigm_env.envX_size - paradigm_env.wallzone_size*60 * 2}
            height={paradigm_env.envY_size - paradigm_env.wallzone_size*60 * 2}
          >
            <!-- <title>PillarID</title> -->
          </rect>
          <rect
            style="fill:none;stroke:var(--fg-color);stroke-width:1;stroke-linecap:butt;stroke-dasharray:2, 4;stroke-dashoffset:0;stroke-opacity:.5"
            id="wallcollider"
            width={paradigm_env.envX_size - paradigm_env.wallzone_size*60}
            height={paradigm_env.envY_size - paradigm_env.wallzone_size*60}
            x={paradigm_env.wallzone_size*60 / 2}
            y={paradigm_env.wallzone_size*60 / 2}
          />

          <path
            id="vertical-path"
            style="stroke:var(--fg-color);stroke-opacity:.1;stroke-width:0.4;stroke-linecap:round;stroke-dasharray:none;stroke-dashoffset:0;"
            d="M 0,0 V {paradigm_env.envY_size}"
          />

          <path
            id="horizontal-path"
            style="stroke:#ffffff;stroke-width:0.409;stroke-linecap:round;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:.2"
            d="M 0,0 H {paradigm_env.envX_size}"
          />
          <!-- GRID -->
          <g>
            {#each Array.from({ length: paradigm_env.envX_size / 10 }, (_, i) => (i + 1) * 10) as vLineXPos}
              <use
                href="#vertical-path"
                transform="translate({vLineXPos}, 0)"
              />
            {/each}

            {#each Array.from({ length: paradigm_env.envY_size / 10 }, (_, i) => (i + 1) * 10) as hLineYPos}
              <use
                href="#horizontal-path"
                transform="translate(0, {hLineYPos})"
              />
            {/each}
          </g>

          {#each Object.values(paradigm_env.pillars) as pillar}
            <g class="pillar" transform="translate({pillar.x}, {pillar.y})">
              <circle
                id="visiblePillar"
                r={paradigm_env.pillar_details[pillar.id].pillarRadius / 2}
                style="fill:#ffe500;fill-opacity:.1;stroke:#ffe500;stroke-width:2;stroke-opacity:1"
              >
                <title>PillarID:{pillar.id}</title>
              </circle>
              <circle
                id="visiblePillar2"
                r={paradigm_env.pillar_details[pillar.id].pillarRewardRadius /
                  2}
                style="fill:none;stroke:#ffe500;stroke-width:1;stroke-opacity:.5;stroke-dasharray:0.682247, 0.282247;"
              />
            </g>
          {/each}

          {#each $unityData as unityFrame, i}
            {#if unityFrame.N === "U"}
              {Object.keys(unityFrame)}

              <circle
                cx={unityFrame.X + paradigm_env.envX_size / 2}
                cy={unityFrame.Z + paradigm_env.envY_size / 2}
                r="2"
                style="fill:var(--fg-color);fill-opacity:{(i * 1) /
                  $unityData.length};fill-rule:evenodd;stroke:#ffffff;stroke-width:0.0187512;stroke-linecap:butt;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1"
              />
            {/if}
          {/each}

          {#if $unityData.length > 0 && $unityData[$unityData.length - 1].N === "U"}
            <g
              id="rat"
              transform="translate({$unityData[$unityData.length - 1].X +
                paradigm_env.envX_size / 2}, {$unityData[$unityData.length - 1]
                .Z +
                paradigm_env.envY_size / 2}) rotate({$unityData[
                $unityData.length - 1
              ].A})"
            >
              <path
                style="fill:none;stroke:var(--fg-color);stroke-width:6;stroke-linecap:butt;stroke-dasharray:none;stroke-dashoffset:0;stroke-opacity:1;marker-start:url(#marker253);marker-end:url(#CapRibbon1)"
                d="m 0,0 2,0"
                id="vector"
              />
              <circle
                id="center"
                r="1.3"
                style="fill:var(--bg-color);fill-opacity:1;fill-rule:evenodd;stroke:none;"
              />
            </g>
          {/if}
        </g></svg
      >
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
    max-width: 600px;
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
</style>
