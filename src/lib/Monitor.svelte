<script>
  import { store } from "../../store/stores";
  import BallVelocityStreamer from "./BallVelocityStreamer.svelte";
  import LickStreamer from "./LickStreamer.svelte";
  import SessionInitiation from "./SessionInitiation.svelte";
  import SessionInterference from "./SessionInterference.svelte";

</script>

<div id="monitor-div" class={$store.showMonitor ? "" : "hide"}>
    <SessionInitiation />
    <SessionInterference />
    <BallVelocityStreamer />
    <LickStreamer />
</div>