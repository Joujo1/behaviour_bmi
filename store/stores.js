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
    showLogfiles: false,
    modalMessage: "",

    // server state
    initiated: true,
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
    por2shm2por: 0,
    facecam2shm: 0,
    bodycam2shm: 0,
    unity: 0,
    log_portenta: 0,
    log_facecam: 0,
    log_bodycam: 0,
    log_unity: 0,
    log_unitycam: 0,
    log_ephys: 0,
    process_session: 0,
    por2shm2por_sim: 0,
    
    // each process' warnings and errors counters
    por2shm2por_warnings: 0,
    facecam2shm_warnings: 0,
    bodycam2shm_warnings: 0,
    unity_warnings: 0,
    log_portenta_warnings: 0,
    log_facecam_warnings: 0,
    log_bodycam_warnings: 0,
    log_unity_warnings: 0,
    log_unitycam_warnings: 0,
    log_ephys_warnings: 0,
    process_session_warnings: 0,
    por2shm2por_sim_warnings: 0,
    
    por2shm2por_errors: 0,
    facecam2shm_errors: 0,
    bodycam2shm_errors: 0,
    unity_errors: 0,
    log_portenta_errors: 0,
    log_facecam_errors: 0,
    log_bodycam_errors: 0,
    log_unity_errors: 0,
    log_unitycam_errors: 0,
    log_ephys_errors: 0,
    process_session_errors: 0,
    por2shm2por_sim_errors: 0,
    
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

