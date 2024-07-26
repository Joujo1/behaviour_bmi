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
        <SessionInitiation />
        <PortentaOutputStreamer />
    </div>
    <div class="row-div">
        <SessionInterference />
        <BallVelocityStreamer />
    </div>
    
    
    <div id="monitor-flex-div">
        <VideoStreamer websocketName="bodycam" title="Overview Camera"/>
        <Environment/>
        <VideoStreamer websocketName="unitycam" title="Unity View"/>

        <ExperimentStateStreamer/>
        <VideoStreamer websocketName="facecam" title="Face Camera"/>

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