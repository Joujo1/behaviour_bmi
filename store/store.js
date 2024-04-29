import { writable } from "svelte/store";

const store = writable({
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
    unitySessionRunning: false,
    // shm interfaces
    termflag_shm_interface: false,
    unityinput_shm_interface: false,
    // shm created
    termflag: false,
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
});

export default store;