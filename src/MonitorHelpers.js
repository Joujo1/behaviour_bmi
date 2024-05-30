import { unityStreamerTRange, unityData, unityXRangeSeconds, store } from "../store/stores";
import { openWebsocket } from "./monitor_api.js";

let unityWScloseCallback = null;

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
    unityData.update(data => data.filter((d, i) => {
        // console.log(d.PCT/1000000)
        return d.PCT/1000000 <= min && d.PCT/1000000 >= max
        // return true;
    }));
}

export function setupUnityWS() {
    if (unityWScloseCallback == null) {
        console.log("setupUnityWS");
        unityWScloseCallback = openWebsocket(
            "unityoutput",
            unityWSOnMessageCallback,
            handleWSHandshakeError
        );
    }
    return unityWScloseCallback;
}

function handleWSHandshakeError(result) {
    unityWScloseCallback();
    unityWScloseCallback = null;
    store.update(value => {
        return {
            ...value,
            showModal: true,
            modalMessage: "Websocket failed to open. Check server for details."
        };
    });
  }