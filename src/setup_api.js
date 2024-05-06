const BASE_URL = "http://0.0.0.0:8001";

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

export async function GETParameters() {
  return fetch(`${BASE_URL}/parameters`)
    .then((response) => response.json())
    .then((data) => {
      // console.log('GET /parameters:', data);
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function GETParameterGroups() {
  return fetch(`${BASE_URL}/parameters/groups`)
    .then((response) => response.json())
    .then((data) => {
      // console.log('GET /parameters/groups:', data);
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function GETLockedParameters() {
  return fetch(`${BASE_URL}/parameters/locked`)
    .then((response) => response.json())
    .then((data) => {
      // console.log('GET /parameters/locked:', data);
      return data;
    })
    .catch((error) => console.error("Error:", error));
}

export async function PATCHParameter(key, new_value) {
  const endpoint = `${BASE_URL}/parameters/${key}?new_value=${new_value}`;
  let response = await fetch(endpoint, { method: "PATCH" });

  let data = await response.json();
  if (!response.ok) {
    const modalMessage =
      `Error - ${endpoint}: Parameter ${key} and value \`${new_value}\`` +
      ` failed with status ${response.status}, ${data.detail}`;
    console.error(modalMessage);
    return modalMessage;
  }
  console.log(
    `Success - ${endpoint}: Patched parameter ${key} with ${new_value}`
  );
  return true;
}

export async function GETServerState() {
  return fetch(`${BASE_URL}/state`)
    .then((response) => response.json())
    .then((data) => {
      return data;
    })
    .catch((error) => console.error("Error:", error));
  }

export const stateEventSource = new EventSource(`${BASE_URL}/statestream`);

export async function POSTInitiate() {
  return await handlePOST(`${BASE_URL}/initiate`);
}

export async function POSTTerminate() {
  return await handlePOST(`${BASE_URL}/raise_term_flag`);
}

export async function POSTFlashPortentaM7() {
  return await handlePOST(`${BASE_URL}/flash_portenta/m7`);
}

export async function POSTFlashPortentaM4() {
  return await handlePOST(`${BASE_URL}/flash_portenta/m4`);
}

export async function POSTCreateTermflag() {
  return await handlePOST(`${BASE_URL}/shm/create_termflag_shm`);
}

export async function POSTCreateBallvelocity() {
  return await handlePOST(`${BASE_URL}/shm/create_ballvelocity_shm`);
}

export async function POSTCreatePortentaoutput() {
  return await handlePOST(`${BASE_URL}/shm/create_portentaoutput_shm`);
}

export async function POSTCreatePortentainput() {
  return await handlePOST(`${BASE_URL}/shm/create_portentainput_shm`);
}

export async function POSTCreateUnityinput() {
  return await handlePOST(`${BASE_URL}/shm/create_unityinput_shm`);
}

export async function POSTCreateUnityoutput() {
  return await handlePOST(`${BASE_URL}/shm/create_unityoutput_shm`);
}

export async function POSTCreateUnitycam() {
  return await handlePOST(`${BASE_URL}/shm/create_unitycam_shm`);
}

export async function POSTCreateFacecam() {
  return await handlePOST(`${BASE_URL}/shm/create_facecam_shm`);
}

export async function POSTCreateBodycam() {
  return await handlePOST(`${BASE_URL}/shm/create_bodycam_shm`);
}

export async function POSTLaunch_por2shm2por_sim() {
  return await handlePOST(`${BASE_URL}/procs/launch_por2shm2por_sim`);
}

export async function POSTLaunch_por2shm2por() {
  return await handlePOST(`${BASE_URL}/procs/launch_por2shm2por`);
}

export async function POSTLaunch_log_portenta() {
  return await handlePOST(`${BASE_URL}/procs/launch_log_portenta`);
}

export async function POSTLaunch_facecam2shm() {
  return await handlePOST(`${BASE_URL}/procs/launch_facecam2shm`);
}

export async function POSTLaunch_bodycam2shm() {
  return await handlePOST(`${BASE_URL}/procs/launch_bodycam2shm`);
}

export async function POSTLaunch_log_facecam() {
  return await handlePOST(`${BASE_URL}/procs/launch_log_facecam`);
}

export async function POSTLaunch_log_bodycam() {
  return await handlePOST(`${BASE_URL}/procs/launch_log_bodycam`);
}

export async function POSTLaunch_log_unity() {
  return await handlePOST(`${BASE_URL}/procs/launch_log_unity`);
}

export async function POSTLaunch_log_unitycam() {
  return await handlePOST(`${BASE_URL}/procs/launch_log_unitycam`);
}

export async function POSTLaunch_stream_bodycam() {
  return await handlePOST(`${BASE_URL}/procs/launch_stream_bodycam`);
}

export async function POSTLaunch_stream_portenta() {
  return await handlePOST(`${BASE_URL}/procs/launch_stream_portenta`);
}

export async function POSTLaunch_unity() {
  return await handlePOST(`${BASE_URL}/procs/launch_unity`);
}