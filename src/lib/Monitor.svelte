<script>
  import store from "../../store/store";
  import BallVelocityStreamer from "./BallVelocityStreamer.svelte";
  import SessionInitiation from "./SessionInitiation.svelte";
  import SessionInterference from "./SessionInterference.svelte";

</script>

<div id="monitor-div" class={$store.showMonitor ? "" : "hide"}>
    <SessionInitiation />
    <SessionInterference />
    <BallVelocityStreamer />
</div>