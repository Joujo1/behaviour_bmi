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