import { unityStreamerTRange, unityData, unityXRangeSeconds, store , unityTrialData, globalT} from "../store/stores.js";
import { openWebsocket } from "./monitor_api.js";

let wsReaders = 0;
let unityWScloseCallback;
let unityWS = null;

let prvGlobalT = 0;
let localGlobalT = 0;

export function unityWSOnMessageCallback(msg) {
    let newData = JSON.parse(msg.data);
    // console.log(newData);

    // get the currently set xRange 
    let xRange;
    let unsubscribe = unityXRangeSeconds.subscribe(value => {
        xRange = value;
    })
    unsubscribe();
    
    let min, max;
    min = newData[newData.length - 1].PCT/1000000;
    max = min - xRange;

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

export function setupUnityWS(oneWay=true) {
    console.log("counter start: " + wsReaders);
    let unityWScloseCallbackWrapper = () => {
        console.log("counter close callback: " + wsReaders);
        wsReaders--;
        if (wsReaders == 0) {
            unityWScloseCallback();
            unityWS = null;
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
        const result = openWebsocket(
            "unityoutput",
            unityWSOnMessageCallback,
            handleWSHandshakeError,
            oneWay
        );
        if (Array.isArray(result)){
            [unityWScloseCallback, unityWS] = result;
        } else {
            unityWScloseCallback = result[0];
        }
    }
    wsReaders++;
    console.log("counter end: " + wsReaders);
    return unityWScloseCallbackWrapper;
    // if (oneWay) {
    //     return unityWScloseCallbackWrapper;
    // } else {
    //     console.log("Returning send callback"); 
    //     return [unityWScloseCallbackWrapper, unityWSsendCallback];
    // }
}

setInterval(() => {
    // send callback is only non null if the websocket was opened with two way communication
    globalT.subscribe(value => {
        localGlobalT = value;
    });
    if (unityWS !== null && localGlobalT !== prvGlobalT && unityWS.readyState > 0) {
        
        const msg = `${prvGlobalT},${localGlobalT}`;
        // console.log("Sent unityoutput request: ", msg);
        unityWS.send(msg);
        prvGlobalT = localGlobalT;
    }
}, 33);