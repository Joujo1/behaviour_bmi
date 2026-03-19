<script>
    import { store } from "../store/stores";
    import { stateEventSource } from "./setup_api";
    import Header from "./lib/Header.svelte";
    import Parameters from "./lib/Parameters.svelte";
    import Setup from "./lib/Setup.svelte";
    import Monitor from "./lib/Monitor.svelte";
    import Modal from "./lib/Modal.svelte";
    import LogViewer from "./lib/LogViewer.svelte";
    import Inspect from "./lib/Inspect.svelte";

    // Function to get the initial state from local storage
    function getInitialState() {
        const savedState = localStorage.getItem("appState");
        if (savedState) {
            return JSON.parse(savedState);
        }
        return {
            // Default state
            inDarkMode: false,
            showParameters: true,
            showSetup: false,
            showMonitor: false,
            showInspect: false,
            showLogfiles: false,
            showModal: false,
            modalMessage: "",
        };
    }

    // Initialize the store with the initial state
    store.set(getInitialState());

    // Function to extract specific fields from the state
    function extractStateFields(state) {
        return {
            inDarkMode: state.inDarkMode,
            showParameters: state.showParameters,
            showSetup: state.showSetup,
            showMonitor: state.showMonitor,
            showInspect: state.showInspect,
            showLogfiles: state.showLogfiles,
            modalMessage: state.modalMessage,
            showModal: false,
        };
    }

    // Subscribe to store changes and save the specific fields to local storage
    store.subscribe((state) => {
        const extractedState = extractStateFields(state);
        localStorage.setItem("appState", JSON.stringify(extractedState));
    });

    function syncServerState2Store(serverState) {
        console.log("Syncing server state to store");

        const updateState = (key, value) => {
            if ($store[key] != value) {
                $store[key] = value;
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
    <LogViewer/>
    <Parameters />
    <Setup />
    <Inspect />
    <Monitor />
</main>

<style>
    main {
        min-width: 1000px; /* Replace with the minimum width you want */
    }
</style>