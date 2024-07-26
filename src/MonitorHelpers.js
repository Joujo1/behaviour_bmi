import { unityStreamerTRange, unityData, unityXRangeSeconds, store , unityTrialData} from "../store/stores";
import { openWebsocket } from "./monitor_api.js";

let wsReaders = 0;
let unityWScloseCallback;

export function unityWSOnMessageCallback(msg) {
    let newData = JSON.parse(msg.data);

    // get the currently set xRange 
    let xRange;
    let unsubscribe = unityXRangeSeconds.subscribe(value => {
        xRange = value;
    })
    unsubscribe();
    
    let min, max;
    // Subscribe to UnityStreamerTRange to get min and max
    unsubscribe = unityStreamerTRange.subscribe(value => {
        min = newData[newData.length - 1].PCT/1000000;
        // console.log(min)
        max = min - xRange;
        // console.log(max)
    });
    unsubscribe();

    // Filter unityData based on min and max
    unityData.update(data => [...data, ...newData]);
    unityData.update(data => data.filter(d => {
        return d.PCT/1000000 >= max
    }));

    unityTrialData.update(data => [...data, ...newData.filter(d => {
        return d.N == "T"
    })]);

    // unsubscribe = unityTrialData.subscribe(value => {
    //     console.log(value)
    // });
    // unsubscribe();
}

export function setupUnityWS() {
    console.log("counter start: " + wsReaders);
    let unityWScloseCallbackWrapper = () => {
        console.log("counter close callback: " + wsReaders);
        wsReaders--;
        if (wsReaders == 0) {
            unityWScloseCallback();
        }
    }

    let handleWSHandshakeError = (result) => {
        unityWScloseCallbackWrapper();
        store.update(value => {
            return {
                ...value,
                showModal: true,
                modalMessage: "Websocket failed to open. Check server for details."
            };
        });
      }

    if (wsReaders == 0) {
        console.log("setupUnityWS");
        unityWScloseCallback = openWebsocket(
            "unityoutput",
            unityWSOnMessageCallback,
            handleWSHandshakeError
        );
    }
    wsReaders++;
    console.log("counter end: " + wsReaders);
    return unityWScloseCallbackWrapper;
}