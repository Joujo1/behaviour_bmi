<script>
import { store } from "../../store/stores";
    import SetupUIButton from "./SetupUIButton.svelte";
    import TickBoxInput from "./TickBoxInput.svelte";
    import MonitorInputField from "./MonitorInputField.svelte";
    import {GETParameters} from "../setup_api.js"
    import {POSTProcessSession} from "../setup_api.js"

    export let isEnabled = true;

    let initiatedState = false;
    let sessionDir = "";
     
    let rnderCamVal = true;
    let integrEphysVal = false;
    let write2DBVal = false;
    let deleteVal = false;
    let copy2NASVal = true;
    let interactiveVal = false;
    let placeholderVal = false;

    function handlePOSTResult(result) {
        console.log(result);
        if (result !== true) {
        $store.showModal = true;
        $store.modalMessage = result;
        }
    }
    async function processSession() {
        const data = {
            sessionDir,
            rnderCamVal,
            integrEphysVal,
            write2DBVal,
            deleteVal,
            copy2NASVal,
            interactiveVal,
            placeholderVal
        };
        console.log(data);
        const result = await POSTProcessSession(data);
        handlePOSTResult(result);
  }

    // when initiated is flipped to True, load the session directory
    $: if (!initiatedState && $store.initiated) {
        async function loadSessionDir () {
            const parameters = await GETParameters();
            sessionDir = parameters["SESSION_DATA_DIRECTORY"];
        };
        loadSessionDir();
        initiatedState = true;
    }


</script>

<div id="postproc-session-div">
    <div class="button-row-div">
        <MonitorInputField label="Session" bind:value={sessionDir} tooltip="sjsdfm" isEnabled={isEnabled} width={300}/>
    </div>
    
    <div class="columns-container">
        <div class="left-column">
            <TickBoxInput label="Render Cams" bind:value={rnderCamVal} tooltip="" isEnabled={isEnabled} width={50}/>
            <TickBoxInput label="Integr. Ephys" bind:value={integrEphysVal} tooltip="" isEnabled={isEnabled} width={50}/>
            <TickBoxInput label="write2DB" bind:value={write2DBVal} tooltip="" isEnabled={isEnabled} width={50}/>
            <TickBoxInput label="Delete" bind:value={deleteVal} tooltip="" isEnabled={isEnabled} width={50}/>
        </div>
        
        <div class="right-column">
            <TickBoxInput label="copy2NAS" bind:value={copy2NASVal} tooltip="" isEnabled={isEnabled} width={50}/>
            <TickBoxInput label="Interactive" bind:value={interactiveVal} tooltip="" isEnabled={isEnabled} width={50}/>
            <TickBoxInput label="placeholder" bind:value={placeholderVal} tooltip="" isEnabled={isEnabled&&false} width={50}/>
            <SetupUIButton
                label="Terminate / Process"
                onClickCallback={() => processSession()}
                isEnabled={isEnabled}
                stateDependancy={$store.process_session} 
                errorsStateDependancy={$store.process_session_errors}
                warningsStateDependancy={$store.process_session_warnings}
                />
        </div>


    </div>
</div>

<style>
    #postproc-session-div {
        display: flex;
        flex-direction: column; /* Stack children vertically */
        justify-content: start;
        align-items: start;
        padding-bottom: 8px;
    }

    .button-row-div {
        display: flex;
        justify-content: start;
        align-items: end;
        flex-direction: row;
        padding-bottom: 8px;
    }

    .columns-container {
        display: flex;
        flex-direction: row; /* Arrange columns side by side */
        width: 100%;
    }

    .left-column, .right-column {
        display: flex;
        flex-direction: column;
        justify-content: start;
        align-items: start;
        flex:1;
    }

    .right-column {
        flex: 0.5
    }

</style>