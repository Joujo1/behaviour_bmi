const BASE_URL = "http://0.0.0.0:8000";

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


  export async function POSTTerminate() {
    return await handlePOST(`${BASE_URL}/raise_term_flag`);
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
