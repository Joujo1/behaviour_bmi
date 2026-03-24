<script>
  import { store } from "../../store/stores";
  import BallVelocityStreamer from "./BallVelocityStreamer.svelte";
  import PortentaOutputStreamer from "./PortentaOutputStreamer.svelte";
  import SessionInitiation from "./SessionInitiation.svelte";
  import SessionInterference from "./SessionInterference.svelte";
  import ExperimentStateStreamer from "./ExperimentStateStreamer.svelte";
  import Environment from "./Environment.svelte";
  import VideoStreamer from "./VideoStreamer.svelte";
  import { style } from "d3";
  import SessionOverview from "./SessionOverview.svelte";

  let testBool = true;
  let currentState = 6;

  // update currentState every 2 seconds to a ranomd int between 0 and 10
  // setInterval(() => {
  //   currentState = Math.floor(Math.random() * 10);
  // }, 2000);

</script>

<div id="monitor-div" class={$store.showMonitor ? "" : "hide"}>
    <div class="row-div">
        {#if !$store.initiatedInspect}
            <SessionInitiation />
        {/if}
        <PortentaOutputStreamer />
    </div>
    <div class="row-div">
        {#if !$store.initiatedInspect}
            <SessionInterference />
        {/if}
        <BallVelocityStreamer />
    </div>
    
    
    <div id="monitor-flex-div">
        <VideoStreamer websocketName="bodycam" title="Overview Camera"/>
        <VideoStreamer websocketName="facecam" title="Face Camera"/>
        <VideoStreamer websocketName="ttlcam2" title="TTL2 Camera"/>
        <VideoStreamer websocketName="ttlcam3" title="TTL3 Camera"/>
        <VideoStreamer websocketName="ttlcam4" title="TTL4 Camera"/>
        {#each [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as cageId}
            <VideoStreamer websocketName="cagecam/{cageId}" title="Cage {cageId}"/>
        {/each}
        <Environment/>
        
        <VideoStreamer websocketName="unitycam" title="Unity View"/>

        <ExperimentStateStreamer/>
        <SessionOverview />


    </div>
</div>

<style>
    
    .row-div {
        display: flex;
        justify-content: start;
        align-items: end;
        flex-direction: row;
        padding-bottom: 3px;
      align-items: flex-start;

    }
    #monitor-div {
        display: flex;
        flex-direction: column;
    }
    #monitor-flex-div {
        display: flex;
        flex-wrap: wrap;
        /* justify-content: space-between; */
        justify-content: start;
        align-items: flex-start;
    }

</style>


<!-- 

<script>
    import { store } from "../../store/stores";
    import BallVelocityStreamer from "./BallVelocityStreamer.svelte";
    import PortentaOutputStreamer from "./PortentaOutputStreamer.svelte";
    import SessionInitiation from "./SessionInitiation.svelte";
    import SessionInterference from "./SessionInterference.svelte";
    import ExperimentStateStreamer from "./ExperimentStateStreamer.svelte";
    import Environment from "./Environment.svelte";
    import VideoStreamer from "./VideoStreamer.svelte";
    import { style } from "d3";
    import SessionOverview from "./SessionOverview.svelte";
  
    let testBool = true;
    let currentState = 6;
  
    // update currentState every 2 seconds to a ranomd int between 0 and 10
    // setInterval(() => {
    //   currentState = Math.floor(Math.random() * 10);
    // }, 2000);
  
    function handleResize(event) {
      const container = event.target.parentElement;
      container.style.width = `${event.target.value}px`;
    }
  </script>
  
  <div id="monitor-div" class={$store.showMonitor ? "" : "hide"}>
      <div class="row-div">
          <div class="resizable">
              <SessionInitiation />
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
          <div class="resizable">
              <PortentaOutputStreamer />
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
      </div>
      <div class="row-div">
          <div class="resizable">
              <SessionInterference />
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
          <div class="resizable">
              <BallVelocityStreamer />
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
      </div>
      
      <div id="monitor-flex-div">
          <div class="resizable">
              <VideoStreamer websocketName="bodycam" title="Overview Camera"/>
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
          <div class="resizable">
              <Environment/>
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
          <div class="resizable">
              <VideoStreamer websocketName="unitycam" title="Unity View"/>
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
          <div class="resizable">
              <ExperimentStateStreamer/>
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
          <div class="resizable">
              <VideoStreamer websocketName="facecam" title="Face Camera"/>
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
          <div class="resizable">
              <SessionOverview />
              <input type="range" min="100" max="800" on:input={handleResize} />
          </div>
      </div>
  </div>
  
  <style>
      .row-div {
          display: flex;
          justify-content: start;
          align-items: end;
          flex-direction: row;
          padding-bottom: 3px;
          align-items: flex-start;
      }
      #monitor-div {
          display: flex;
          flex-direction: column;
      }
      #monitor-flex-div {
          display: flex;
          flex-wrap: wrap;
          justify-content: start;
          align-items: flex-start;
      }
      .resizable {
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: stretch;
          margin: 5px;
      }
      .resizable input[type="range"] {
          position: absolute;
          bottom: 0;
          left: 0;
          width: 100%;
      }
  </style> -->