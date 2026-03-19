<script>
    import { store } from "../../store/stores";
  import SessionSelection from "./SessionSelection.svelte";
  import SessionTimeline from "./SessionTimeline.svelte";

</script>

<div id="inspect-div" class={$store.showInspect ? "" : "hide"}>
        <SessionSelection />
        <SessionTimeline />

</div>

<style>
     /* app.css definition doesn't work ?? */
    #inspect-div{
        display: flex;
        /* justify-content: space-between; */
        justify-content: start;
        align-items: flex-start;

        transition: all 0.1s ease-in-out;
        border-bottom: 1px solid var(--fg-color);
        margin-left: 15px;
        margin-right: 15px;
        padding-top: 15px;
        padding-bottom: 15px;
        }
    

</style>