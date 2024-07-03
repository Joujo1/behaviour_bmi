const BASE_URL = "http://0.0.0.0:8000";
const WS_BASE_URL = "ws://0.0.0.0:8000/stream";

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

export async function GETAnimals() {
  return fetch(`${BASE_URL}/animals`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function POSTAnimal(msg) {
  return await handlePOST(`${BASE_URL}/session/animal/${msg}`)
}

export async function POSTAnimalWeight(msg) {
  return await handlePOST(`${BASE_URL}/session/animalweight/${msg}`)
}

export async function POSTSessionNotes(msg) {
  return await handlePOST(`${BASE_URL}/session/notes/${msg}`)
}

export function openWebsocket(wsName, onMessageCallback = () => {},
                              onErrorCallback = (event) => {console.error(event)}) {
  var url = `${WS_BASE_URL}/${wsName}`
  var ws = new WebSocket(url)
  ws.onerror = onErrorCallback
  ws.onmessage = onMessageCallback
  console.debug("WebSocket opened:", ws)

  let closeCallback = () => {
    console.debug("WebSocket closed:", ws)
    ws.close()
  }
  return closeCallback
}

// export async function GETParadigmsFSMs() {
//   return fetch(`${BASE_URL}/paradigm_fsm`)
//     .then((response) => response.json())
//     .then((data) => {
//       return data;
//     })
//     .catch((error) => console.error("Error:", error))
//     .then((data) => {
//       data.response = 400;
//       return data;
//     });

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