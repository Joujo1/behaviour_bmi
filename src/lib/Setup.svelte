<script>
  import store from "../../store/store";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import { GETServerState, POSTInitiate, POSTTerminate } from "../setup_api";
  import { POSTFlashPortentaM4, POSTFlashPortentaM7 } from "../setup_api";
  import { POSTCreateTermflag } from "../setup_api";
  import {
    POSTCreateBallvelocity,
    POSTCreatePortentaoutput,
    POSTCreatePortentainput,
  } from "../setup_api";
  import { POSTCreateUnityinput, POSTCreateUnityoutput } from "../setup_api";
  import {
    POSTCreateUnitycam,
    POSTCreateFacecam,
    POSTCreateBodycam,
  } from "../setup_api";

  import {
    POSTLaunch_por2shm2por,
    POSTLaunch_log_portenta,
    POSTLaunch_log_unity,
  } from "../setup_api";
  import {
    POSTLaunch_facecam2shm,
    POSTLaunch_bodycam2shm,
    POSTLaunch_log_facecam,
    POSTLaunch_log_bodycam,
  } from "../setup_api";
  import {
    POSTLaunch_log_unitycam,
    POSTLaunch_por2shm2por_sim,
  } from "../setup_api";

  import SetupUiButton from "./SetupUIButton.svelte";

  function handlePOSTResult(result) {
    console.log(result);
    if (result !== true) {
      $store.showModal = true;
      $store.modalMessage = result;
    }
  }

  async function initiate() {
    const result = await POSTInitiate();
    handlePOSTResult(result);
  }

  async function terminate() {
    const result = await POSTTerminate();
    handlePOSTResult(result);
  }

  async function flashPortentaM7() {
    const result = await POSTFlashPortentaM7();
    handlePOSTResult(result);
  }

  async function flashPortentaM4() {
    const result = await POSTFlashPortentaM4();
    handlePOSTResult(result);
  }

  async function createTermflag() {
    const result = await POSTCreateTermflag();
    handlePOSTResult(result);
  }

  async function createBallvelocity() {
    const result = await POSTCreateBallvelocity();
    handlePOSTResult(result);
  }

  async function createPortentaoutput() {
    const result = await POSTCreatePortentaoutput();
    handlePOSTResult(result);
  }

  async function createPortentainput() {
    const result = await POSTCreatePortentainput();
    handlePOSTResult(result);
  }

  async function createUnityinput() {
    const result = await POSTCreateUnityinput();
    handlePOSTResult(result);
  }

  async function createUnityoutput() {
    const result = await POSTCreateUnityoutput();
    handlePOSTResult(result);
  }

  async function createUnitycam() {
    const result = await POSTCreateUnitycam();
    handlePOSTResult(result);
  }

  async function createFacecam() {
    const result = await POSTCreateFacecam();
    handlePOSTResult(result);
  }

  async function createBodycam() {
    const result = await POSTCreateBodycam();
    handlePOSTResult(result);
  }

  async function createAll() {
    createTermflag();
    createBallvelocity();
    createPortentaoutput();
    createPortentainput();
    createUnityinput();
    createUnityoutput();
    createUnitycam();
    createFacecam();
    createBodycam();
  }

  async function launch_por2shm2por_sim() {
    const result = await POSTLaunch_por2shm2por_sim();
    handlePOSTResult(result);
  }

  async function launch_por2shm2por() {
    const result = await POSTLaunch_por2shm2por();
    handlePOSTResult(result);
  }

  async function launch_log_portenta() {
    const result = await POSTLaunch_log_portenta();
    handlePOSTResult(result);
  }

  async function launch_facecam2shm() {
    const result = await POSTLaunch_facecam2shm();
    handlePOSTResult(result);
  }

  async function launch_bodycam2shm() {
    const result = await POSTLaunch_bodycam2shm();
    handlePOSTResult(result);
  }

  async function launch_log_facecam() {
    const result = await POSTLaunch_log_facecam();
    handlePOSTResult(result);
  }

  async function launch_log_bodycam() {
    const result = await POSTLaunch_log_bodycam();
    handlePOSTResult(result);
  }

  async function launch_log_unity() {
    const result = await POSTLaunch_log_unity();
    handlePOSTResult(result);
  }

  async function launch_log_unitycam() {
    const result = await POSTLaunch_log_unitycam();
    handlePOSTResult(result);
  }
</script>

<div id="setup-div" class={$store.showSetup ? "" : "hide"}>
  <SetupUIBlock>
    <div slot="header">General control</div>
    <div slot="setupui">
      <div class="button-row-div">
        <SetupUIButton
          label="Initiate"
          onClickCallback={initiate}
          stateDependancy={$store.initiated}
        />
        <SetupUIButton label="Terminate" onClickCallback={terminate} />
      </div>
      <div class="button-row-div">
        <SetupUIButton
          label="Flash Portenta M7"
          onClickCallback={flashPortentaM7}
        />
        <SetupUIButton
          label="Flash Portenta M4"
          onClickCallback={flashPortentaM4}
        />
      </div>
    </div></SetupUIBlock
  >

  <SetupUIBlock>
    <div slot="header">Create shared memory</div>
    <div slot="setupui">
      <div class="button-row-div">
        <SetupUIButton
          label="termflag"
          onClickCallback={createTermflag}
          stateDependancy={$store.termflag}
        />
      </div>
      <div class="button-row-div">
        <SetupUIButton
          label="ballvelocity"
          onClickCallback={createBallvelocity}
          stateDependancy={$store.ballvelocity}
        />
        <SetupUIButton
          label="portentaoutput"
          onClickCallback={createPortentaoutput}
          stateDependancy={$store.portentaoutput}
        />
        <SetupUIButton
          label="portentainput"
          onClickCallback={createPortentainput}
          stateDependancy={$store.portentainput}
        />
      </div>
      <div class="button-row-div">
        <SetupUIButton
          label="unityinput"
          onClickCallback={createUnityinput}
          stateDependancy={$store.unityinput}
        />
        <SetupUIButton
          label="unityoutput"
          onClickCallback={createUnityoutput}
          stateDependancy={$store.unityoutput}
        />
      </div>
      <div class="button-row-div">
        <SetupUIButton
          label="unitycam"
          onClickCallback={createUnitycam}
          stateDependancy={$store.unitycam}
        />
        <SetupUIButton
          label="facecam"
          onClickCallback={createFacecam}
          stateDependancy={$store.facecam}
        />
        <SetupUIButton
          label="bodycam"
          onClickCallback={createBodycam}
          stateDependancy={$store.bodycam}
        />
        <SetupUIButton label="/all" onClickCallback={createAll} />
      </div>
    </div></SetupUIBlock
  >
  <SetupUIBlock>
    <div slot="header">Launch Processes</div>
    <div slot="setupui">
      <div class="button-row-div">
        <SetupUiButton
          label="por2shm2por"
          onClickCallback={launch_por2shm2por}
          stateDependancy={$store.por2shm2por}
        />
        <SetupUiButton
          label="log_portenta"
          onClickCallback={launch_log_portenta}
          stateDependancy={$store.log_portenta}
        />
        <SetupUiButton
          label="log_unity"
          onClickCallback={launch_log_unity}
          stateDependancy={$store.log_unity}
        />
      </div>
      <div class="button-row-div">
        <SetupUiButton
          label="facecam2shm"
          onClickCallback={launch_facecam2shm}
          stateDependancy={$store.facecam2shm}
        />
        <SetupUiButton
          label="bodycam2shm"
          onClickCallback={launch_bodycam2shm}
          stateDependancy={$store.bodycam2shm}
        />
        <SetupUiButton
          label="log_facecam"
          onClickCallback={launch_log_facecam}
          stateDependancy={$store.log_facecam}
        />
        <SetupUiButton
          label="log_bodycam"
          onClickCallback={launch_log_bodycam}
          stateDependancy={$store.log_bodycam}
        />
      </div>
      <div class="button-row-div">
        <SetupUiButton
          label="log_unitycam"
          onClickCallback={launch_log_unitycam}
          stateDependancy={$store.log_unitycam}
        />
      </div>
      <div class="button-row-div">
        <SetupUiButton
          label="por2shm2por_sim"
          onClickCallback={launch_por2shm2por_sim}
          stateDependancy={$store.por2shm2por_sim}
        />
      </div>
    </div></SetupUIBlock
  >
</div>

<style>
  .button-row-div {
    display: flex;
    justify-content: start;
    align-items: end;
    flex-direction: row;
    padding-bottom: 8px;
  }
</style>
