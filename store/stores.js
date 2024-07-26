import { derived, readable, writable } from "svelte/store";
import { extent } from "d3";

export const store = writable({
    //ui state
    inDarkMode: false,
    showParameters: true,
    showSetup: false,
    showMonitor: false,
    showAnalyze: false,
    showModal: false,
    modalMessage: "",

    // server state
    initiated: false,
    paradigmRunning: false,
    // shm interfaces
    termflag_shm_interface: false,
    unityinput_shm_interface: false,
    paradigm_running_shm_interface: false,
    // shm created
    termflag: false,
    paradigmflag: false,
    ballvelocity: false,
    portentaoutput: false,
    portentainput: false,
    unityoutput: false,
    unityinput: false,
    unitycam: false,
    facecam: false,
    bodycam: false, 
    // processes running (PID)
    por2shm2por_sim: 0,
    por2shm2por: 0,
    log_portenta: 0,
    facecam2shm: 0,
    bodycam2shm: 0,
    log_facecam: 0,
    log_bodycam: 0,
    log_unity: 0,
    log_unitycam: 0,
    unity: 0,
    process_session: 0,
});

export const ballvelocityData = writable([]);
export const portentaData = writable([]);
export const PortentaStreamerTRange = writable({
    min: -1,
    max: -1,
});

export const unityData = writable([]);
export const unityStreamerTRange = writable({
    min: -1,
    max: -1,
});
export const unityTrialData = writable([]);
export const unityXRangeSeconds = writable(5);

