<script>
    import { store } from "../store/stores";
    import {stateEventSource} from "./setup_api";
    import Header from "./lib/Header.svelte";
    import Parameters from "./lib/Parameters.svelte";
    import Setup from "./lib/Setup.svelte";
    import Monitor from "./lib/Monitor.svelte";
    import Modal from "./lib/Modal.svelte";

    function syncServerState2Store(serverState) {
        // console.log("Syncing server state to store:", serverState);
        console.log("Syncing server state to store");

        const updateState = (key, value) => {
        if ($store[key] != value) {
            $store[key] = value;
            console.log(`State updated - ${key}:${value}`);
        }
        };

        Object.entries(serverState).forEach(([key, value]) => {
        if (key === "shm" || key === "procs") {
            Object.entries(value).forEach(([subkey, subvalue]) => {
            updateState(subkey, subvalue);
            });
        } else {
            updateState(key, value);
        }
        });
    }
        
    stateEventSource.onmessage = function(event) {
        syncServerState2Store(JSON.parse(event.data));
    };

</script>

<main class={$store.inDarkMode ? "darkm" : "lightm"}>
    <Header />
    {#if $store.showModal}
        <Modal/>
    {/if}
    <Parameters />
    <Setup />
    <Monitor />
</main>

<style>
    main {
        min-width: 1000px; /* Replace with the minimum width you want */
    }
</style>