<script>
  import { store } from "../../store/stores";
  import SetupUIBlock from "./SetupUIBlock.svelte";
  import SetupUIButton from "./SetupUIButton.svelte";
  import ProcessSessionCard from "./ProcessSessionCard.svelte";
  import { GETServerState, GETcheckNAS, POSTInitiate } from "../setup_api";
  import { POSTFlashPortentaM4, POSTFlashPortentaM7 } from "../setup_api";
  import { POSTCreateTermflag,
           POSTCreateParadigmRunningFlag,
   } from "../setup_api";
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
    POSTLaunch_log_ephys,
  } from "../setup_api";
  import {
    POSTLaunch_log_unitycam,
    POSTLaunch_por2shm2por_sim,
  } from "../setup_api";
  import {
    POSTLaunch_stream_bodycam,
    POSTLaunch_face_bodycam,
    POSTLaunch_stream_portenta,
  } from "../setup_api";
  
  import { POSTLaunch_unity,
           POSTLaunch_scope,
           POSTLaunch_mxserver,
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
    let result = await POSTInitiate();
    handlePOSTResult(result);

    result = await GETcheckNAS();
    console.log(result);
    handlePOSTResult(result);
  }

  // async function terminate(post_term_action = "none") {
  //   const result = await POSTTerminate(post_term_action);
  //   handlePOSTResult(result);
  // }

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
  
  async function createParadigmRunningFlag() {
    const result = await POSTCreateParadigmRunningFlag();
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
    createParadigmRunningFlag();
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
  
  async function launch_log_ephys() {
    const result = await POSTLaunch_log_ephys();
    handlePOSTResult(result);
  }
  
  async function launch_all_processes() {
  let result;
  result = await POSTLaunch_por2shm2por();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_facecam2shm();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_bodycam2shm();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_unity();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_log_portenta();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_log_unity();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_log_unitycam();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_log_facecam();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_log_bodycam();
  handlePOSTResult(result);
  await new Promise(r => setTimeout(r, 100));
  result = await POSTLaunch_log_ephys();
  handlePOSTResult(result);
  }

  async function launch_stream_bodycam() {
    const result = await POSTLaunch_stream_bodycam();
    handlePOSTResult(result);
  }

  async function launch_face_bodycam() {
    const result = await POSTLaunch_face_bodycam();
    handlePOSTResult(result);
  }

  async function launch_stream_portenta() {
    const result = await POSTLaunch_stream_portenta();
    handlePOSTResult(result);
  }

  async function launch_unity() {
    const result = await POSTLaunch_unity();
    handlePOSTResult(result);
  }
  
  async function launch_mxserver() {
    const result = await POSTLaunch_mxserver();
    handlePOSTResult(result);
  }
  
  async function launch_scope() {
    const result = await POSTLaunch_scope();
    handlePOSTResult(result);
  }
</script>

<div id="setup-div" class={$store.showSetup ? "" : "hide"}>
  <div class=left-column>
    <SetupUIBlock>
      <div slot="header">Base Control</div>
      <div slot="setupui">
        <div class="button-row-div">
          <SetupUIButton
            label="Initiate"
            onClickCallback={initiate}
            stateDependancy={$store.initiated}
          />
          <SetupUIButton
            label="Flash Portenta M7"
            onClickCallback={flashPortentaM7}
          />
          <SetupUIButton
            label="Flash Portenta M4"
            onClickCallback={flashPortentaM4}
          />
        </div>
        <div class="button-row-div">
          
        </div>
      </div></SetupUIBlock>

      <SetupUIBlock>
      <div slot="header">Post-Process</div>
      <div slot="setupui">
        <ProcessSessionCard isEnabled={$store.initiated && !$store.paradigmRunning}
        />
        
      </div></SetupUIBlock>
    </div>


  <div class=right-column>
    <SetupUIBlock>
      <div slot="header">Create shared memory</div>
      <div slot="setupui">
        <div class="button-row-div">
          <SetupUIButton
            label="termflag"
            onClickCallback={createTermflag}
            stateDependancy={$store.termflag}
          />
          <SetupUIButton
            label="paradigmrunningflag"
            onClickCallback={createParadigmRunningFlag}
            stateDependancy={$store.paradigmflag}
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
            warningsStateDependancy={$store.por2shm2por_warnings}
            errorsStateDependancy={$store.por2shm2por_errors}
          />
          <SetupUiButton
            label="facecam2shm"
            onClickCallback={launch_facecam2shm}
            stateDependancy={$store.facecam2shm}
            warningsStateDependancy={$store.facecam2shm_warnings}
            errorsStateDependancy={$store.facecam2shm_errors}
          />
          <SetupUiButton
            label="bodycam2shm"
            onClickCallback={launch_bodycam2shm}
            stateDependancy={$store.bodycam2shm}
            warningsStateDependancy={$store.bodycam2shm_warnings}
            errorsStateDependancy={$store.bodycam2shm_errors}
          />
        </div>

        <div class="button-row-div">
          <SetupUiButton
            label="unity"
            onClickCallback={launch_unity}
            stateDependancy={$store.unity}
            warningsStateDependancy={$store.unity_warnings}
            errorsStateDependancy={$store.unity_errors}
          />
          <SetupUiButton
            label="mxserver"
            onClickCallback={launch_mxserver}
            stateDependancy={$store.mxserver}
          />
          <SetupUiButton
            label="scope"
            onClickCallback={launch_scope}
            stateDependancy={$store.scope}
          />
        </div>

        <div class="button-row-div">
          <SetupUiButton
            label="log_portenta"
            onClickCallback={launch_log_portenta}
            stateDependancy={$store.log_portenta}
            warningsStateDependancy={$store.log_portenta_warnings}
            errorsStateDependancy={$store.log_portenta_errors}
          />
          <SetupUiButton
            label="log_unity"
            onClickCallback={launch_log_unity}
            stateDependancy={$store.log_unity}
            warningsStateDependancy={$store.log_unity_warnings}
            errorsStateDependancy={$store.log_unity_errors}
          />
          <SetupUiButton
            label="log_unitycam"
            onClickCallback={launch_log_unitycam}
            stateDependancy={$store.log_unitycam}
            warningsStateDependancy={$store.log_unitycam_warnings}
            errorsStateDependancy={$store.log_unitycam_errors}
          />
        </div>
        <div class="button-row-div">
          <SetupUiButton
            label="log_facecam"
            onClickCallback={launch_log_facecam}
            stateDependancy={$store.log_facecam}
            warningsStateDependancy={$store.log_facecam_warnings}
            errorsStateDependancy={$store.log_facecam_errors}
          />
          <SetupUiButton
            label="log_bodycam"
            onClickCallback={launch_log_bodycam}
            stateDependancy={$store.log_bodycam}
            warningsStateDependancy={$store.log_bodycam_warnings}
            errorsStateDependancy={$store.log_bodycam_errors}
          />
          <SetupUiButton
            label="log_ephys"
            onClickCallback={launch_log_ephys}
            stateDependancy={$store.log_ephys}
            warningsStateDependancy={$store.log_ephys_warnings}
            errorsStateDependancy={$store.log_ephys_errors}
          />
          <SetupUiButton
            label="/all"
            onClickCallback={launch_all_processes}
          />
        </div>
        <div class="button-row-div">
          <!-- <SetupUiButton
            label="stream_portenta"
            onClickCallback={launch_stream_portenta}
          />
          <SetupUiButton
            label="stream_bodycam"
            onClickCallback={launch_stream_bodycam}
            isEnabled={false}
          />
          <SetupUiButton
            label="stream_facecam"
            onClickCallback={launch_face_bodycam}
            isEnabled={false}
          /> -->
        </div>
        <div class="button-row-div">
          <SetupUiButton
            label="por2shm2por_sim"
            onClickCallback={launch_por2shm2por_sim}
            stateDependancy={$store.por2shm2por_sim}
          />
      </div>
    </div></SetupUIBlock>
  </div>
</div>

<style>

#setup-div {
    display: flex;
    flex-wrap: wrap;
    /* justify-content: space-between; */
    justify-content: start;
    align-items: flex-start;

    transition: all 0.1s ease-in-out;
    border-bottom: 1px solid var(--fg-color);
    margin-left: 15px;
    margin-right: 15px;
    padding-top: 15px;
    padding-bottom: 15px;
  }
 #setup-div.hide {
  opacity: 0;
  transform: translateX(-100%);
  height: 0;
  padding: 0;
  border-bottom: none;
}

  .button-row-div {
    display: flex;
    justify-content: start;
    align-items: end;
    flex-direction: row;
    padding-bottom: 8px;
  }

  .left-column, .right-column {
    display: flex;
    justify-content: start;
    align-items: end;
    align-items: start;

  }

  .left-column {
    flex-direction: column;
    width: 500px;
  }
  .right-column {
    flex-direction: row;

    /* width: 430px; */
  }
</style>
