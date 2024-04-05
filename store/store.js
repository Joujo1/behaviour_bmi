import { writable } from "svelte/store";

const store = writable({
    inDarkMode: false,
    showParameters: true,
    showSetup: false,
    showMonitor: false,
    showAnalyze: false,
});

export default store;