import { store } from "../store/stores";

const BASE_URL = "http://0.0.0.0:8000";

// async function handlePOST(endpoint) {
//   let response = await fetch(endpoint, { method: "POST" });
//   let data = await response.json();
//   if (!response.ok) {
//     const modalMessage = `Error - ${endpoint}: failed with status `+
//                           `${response.status}, ${data.detail}`;
//     console.error(modalMessage);
//     return modalMessage;
//   }
//   console.log(`Success - ${endpoint}`);
//   return true;
// }

// export async function POSTUnityInput(msg) {
//     return await handlePOST(`${BASE_URL}/unityinput/${msg}`)
// }

export async function GETSessions() {
  return fetch(`${BASE_URL}/inspect/sessions`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function GETCurrentSession() {
  return fetch(`${BASE_URL}/inspect/selected_session`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function POSTSessionSelection(msg) {
  return fetch(`${BASE_URL}/inspect/initiate_session_selection/${msg}`, { method: "POST" })
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function POSTTerminateInspection() {
  return fetch(`${BASE_URL}/inspect/terminate_inspection`, { method: "POST" })
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
}
export async function GETTrials() {
  return fetch(`${BASE_URL}/inspect/trials`)
    .then((response) => response.json())
    .then((data) => {
      return JSON.parse(data);
    })
    .catch((error) => console.error("Error:", error));
  }

  export async function GETEvents() {
    return fetch(`${BASE_URL}/inspect/events`)
      .then((response) => response.json())
      .then((data) => {
        return JSON.parse(data);
      })
      .catch((error) => console.error("Error:", error));
  }
  
  export async function GETForwardVelocity() {
    return fetch(`${BASE_URL}/inspect/forwardvelocity`)
      .then((response) => response.json())
      .then((data) => {
        return JSON.parse(data);
      })
      .catch((error) => console.error("Error:", error));
  }
  
  export async function GETUnityFrames() {
    return fetch(`${BASE_URL}/inspect/unityframes`)
      .then((response) => response.json())
      .then((data) => {
        return data;
      })
      .catch((error) => console.error("Error:", error));
  }