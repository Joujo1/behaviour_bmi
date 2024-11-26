import { unityStreamerTRange, unityData, unityXRangeSeconds, store , unityTrialData, globalT, portentaData, } from "../store/stores.js";
import { trialUnityVelData, trialPortentaEventData} from "../store/stores.js";
import { openWebsocket } from "./monitor_api.js";

let wsReaders = 0;
let unityWScloseCallback;
let unityWS = null;

let prvGlobalT = 0;
let localGlobalT = 0;

let curPortentaEvent = {}
let curTrial = {}

export function unityWSOnMessageCallback(msg) {
    let newData = JSON.parse(msg.data);
    // console.log(newData);

    // get the currently set xRange 
    let xRange;
    let unsubscribe;
    unsubscribe = unityXRangeSeconds.subscribe(value => {
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

    // get the last 10 unity frames from unityData and calculate the velocity, 
    // append to trialUnityVelData store
    let last10Frames = [];
    unsubscribe = unityData.subscribe(data => {
        last10Frames = data.slice(Math.max(data.length - 10, 0));
    });
    unsubscribe();

    const timeinterval = (last10Frames[last10Frames.length - 1].PCT - last10Frames[0].PCT) / 1000000;
    const distance = last10Frames[last10Frames.length - 1].Z - last10Frames[0].Z;
    const frameVelocity = distance / timeinterval;
    const cur_position = last10Frames[last10Frames.length - 1].Z;
    trialUnityVelData.update(data => [...data, {frameVelocity, cur_position}]);

    // TODO: should rather be updated when new portenta event is received
    let lastEvent = {};
    unsubscribe = portentaData.subscribe(data => {
        lastEvent = data[data.length - 1];
    });
    unsubscribe();
    // console.log("lastEvent", lastEvent);
    if (lastEvent && lastEvent !== curPortentaEvent) {
        trialPortentaEventData.update(data => [...data, {N: lastEvent.N, cur_position}]);
        curPortentaEvent = lastEvent; // update the current/ last portenta event
    }


    // clear the trial data stores if a new trial has started
    let lastTrial = {};
    unsubscribe = unityTrialData.subscribe(data => {
        lastTrial = data[data.length - 1];
    });
    unsubscribe();
    // console.log("lastTrial", lastTrial, "curTrial", curTrial);
    if (lastTrial !== curTrial) {
        console.log("New TrialData", curTrial);
        // trialPortentaEventData.update(data => [...data, {N: "T", cur_position}]);
        curTrial = lastTrial;
        setTimeout(() => {
            trialUnityVelData.set([]);
            trialPortentaEventData.set([]);
        }, 1000);
    }

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