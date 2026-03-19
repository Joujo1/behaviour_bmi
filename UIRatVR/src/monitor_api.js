import { store } from "../store/stores";

const BASE_URL = "http://127.0.0.1:8000";
const WS_BASE_URL = "ws://127.0.0.1:8000/stream";

let wsReaderCounters = {};
let wsCloseCallbacks = {};

async function handlePOST(endpoint) {
  let response = await fetch(endpoint, { method: "POST" });
  let data = await response.json();
  if (!response.ok) {
    const modalMessage = `Error - ${endpoint}: failed with status `+
                          `${response.status}, ${data.detail}`;
    console.error(modalMessage);
    return modalMessage;
  }
  console.log(`Success - ${endpoint}`);
  return true;
}

export async function POSTUnityInput(msg) {
    return await handlePOST(`${BASE_URL}/unityinput/${msg}`)
}

export async function GETParadigms() {
  return fetch(`${BASE_URL}/paradigms`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function GETSelectedParadigm() {
  return fetch(`${BASE_URL}/selected_paradigm`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function GETSelectedAnimal() {
  return fetch(`${BASE_URL}/selected_animal`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function GETAnimals() {
  return fetch(`${BASE_URL}/animals`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
  }
  
export async function GETTrialVarialbeNames() {
  return fetch(`${BASE_URL}/trial_variable_names`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}
    
export async function GETTrialVarialbeDefaultValues() {
  return fetch(`${BASE_URL}/trial_variable_default_values`)
  .then((response) => response.json())
  .then((data) => {
    return data;
  })
  .catch((error) => console.error("Error:", error));
}

export async function GETSessionStartTime() {
  return fetch(`${BASE_URL}/session_start_time`)
  .then((response) => response.json())
  .then((data) => {
    return data;
  })
  .catch((error) => console.error("Error:", error));
}

export async function POSTParadigm(msg) {
  return await handlePOST(`${BASE_URL}/session/paradigm/${msg}`)
}
      
export async function POSTAnimal(msg) {
  return await handlePOST(`${BASE_URL}/session/animal/${msg}`)
}

export async function POSTAnimalWeight(msg) {
  return await handlePOST(`${BASE_URL}/session/animalweight/${msg}`)
}

export async function POSTStartParadigm() {
  return await handlePOST(`${BASE_URL}/start_paradigm`)
}

export async function POSTStopParadigm() {
  return await handlePOST(`${BASE_URL}/stop_paradigm`)
}

export async function POSTSessionNotes(msg) {
  return await handlePOST(`${BASE_URL}/session/notes/${msg}`)
}

export function openWebsocket(wsName, onMessageCallback = () => {},
                              onErrorCallback = (event) => {console.error(event)},
                              oneWay = true,
) {
  if (oneWay) {
    var url = `${WS_BASE_URL}/${wsName}`
  } else {
    var url = `${WS_BASE_URL}/${wsName}?inspect=true`;
  }

  var ws = new WebSocket(url)
  ws.onerror = onErrorCallback
  ws.onmessage = onMessageCallback
  console.debug("WebSocket opened:", ws)
  
  let closeCallback = () => {
    console.debug("WebSocket closed:", ws)
    ws.close()
  }
  if (oneWay) {
    return closeCallback
  }
  // let sendCallback = (msg) => ws.send(msg)
  return [closeCallback, ws]
}

// ms input
export function time2str(t) {
  const date = new Date(t);
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');
  const milliseconds = date.getMilliseconds().toString().padStart(3, '0');
  return `${minutes}:${seconds}:${milliseconds}`;
  // return `${seconds}:${milliseconds}s`;
}

// handle multiple readers of the same websocket, only close when all readers are done
export function openCountedWebsocket(wsName, onMessageCallback) {
  if (wsReaderCounters[wsName] == undefined) {
    wsReaderCounters[wsName] = 0;
  }

  console.log("counter " +wsName+ "WS start: " + wsReaderCounters[wsName]);
  let wsCloseCallbackWrapper = () => {
      console.log("counter within close callback for "+wsName+"WS: " + wsReaderCounters[wsName]);
      wsReaderCounters[wsName]--;
      if (wsReaderCounters[wsName] == 0) {
        wsCloseCallbacks[wsName]();
      }
  }

  let handleWSHandshakeError = (result) => {
      console.log("counter within handshake error for "+wsName+"WS: " + wsReaderCounters[wsName]);
      wsCloseCallbackWrapper();
      store.update(value => {
          return {
              ...value,
              showModal: true,
              modalMessage: "Websocket "+wsName+" failed to open. Check server for details."
          };
      });
    }

  if (wsReaderCounters[wsName] == 0) {
      wsCloseCallbacks[wsName] = openWebsocket(
          wsName,
          onMessageCallback,
          handleWSHandshakeError
      );
  }
  wsReaderCounters[wsName]++;
  console.log("counter "+wsName+" end: " + wsReaderCounters[wsName]);
  return wsCloseCallbackWrapper;
}

export async function GETParadigmsFSMs() {
  let endpoint = `${BASE_URL}/paradigm_fsm`;
  let response = await fetch(endpoint, { method: "GET" });
  let data = await response.json();
  if (!response.ok) {
    const modalMessage = `Error - ${data.detail}`;
    console.error(modalMessage);
    return modalMessage;
  }
  return data;
}

export async function GETParadigmsEnvironement() {
  let endpoint = `${BASE_URL}/paradigm_env`;
  let response = await fetch(endpoint, { method: "GET" });
  let data = await response.json();
  if (!response.ok) {
    const modalMessage = `Error - ${data.detail}`;
    console.error(modalMessage);
    return modalMessage;
  }
  return data;
}