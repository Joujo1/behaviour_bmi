<script>
  import { store } from "../../store/stores";
  import BallVelocityStreamer from "./BallVelocityStreamer.svelte";
  import PortentaOutputStreamer from "./PortentaOutputStreamer.svelte";
  import SessionInitiation from "./SessionInitiation.svelte";
  import SessionInterference from "./SessionInterference.svelte";
  import ExperimentStateStreamer from "./ExperimentStateStreamer.svelte";
  import Environment from "./Environment.svelte";

  let testBool = true;
  let currentState = 6;

  // update currentState every 2 seconds to a ranomd int between 0 and 10
  // setInterval(() => {
  //   currentState = Math.floor(Math.random() * 10);
  // }, 2000);

</script>

<div id="monitor-div" class={$store.showMonitor ? "" : "hide"}>
    <SessionInitiation />
    <SessionInterference />
    <BallVelocityStreamer />
    <PortentaOutputStreamer />
    <ExperimentStateStreamer currentState={currentState}/>
    <Environment/>
</div>