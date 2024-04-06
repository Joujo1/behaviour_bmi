<script>
  import store from "../../store/store";
  import ParameterCard from "./ParameterCard.svelte";
  import { onMount } from "svelte";

  let base_url = "http://0.0.0.0:8000";

  function getParameters() {
    return fetch(`${base_url}/parameters`)
      .then((response) => response.json())
      .then((data) => {
        // console.log('GET /parameters:', data);
        return data;
      })
      .catch((error) => console.error("Error:", error));
  }

  function getParameterGroups() {
    return fetch(`${base_url}/parameters/groups`)
      .then((response) => response.json())
      .then((data) => {
        // console.log('GET /parameters/groups:', data);
        return data;
      })
      .catch((error) => console.error("Error:", error));
  }

  function getLockedParameters() {
    return fetch(`${base_url}/parameters/locked`)
      .then((response) => response.json())
      .then((data) => {
        // console.log('GET /parameters/locked:', data);
        return data;
      })
      .catch((error) => console.error("Error:", error));
  }

  // let allCardParams;
  // const allCardParams = {"string": {"string": 3}}

  async function getLockedParams() {
    const lockedParams = await getLockedParameters();
    return lockedParams;
  }

  async function getAllCardParams() {
    const params = await getParameters();
    console.log(params);
    const paramGroups = await getParameterGroups();
    console.log(paramGroups);
    console.log("========");

    const allCardParams = Object.entries(paramGroups).reduce(
      (acc, [groupName, group]) => {
        acc[groupName] = group.reduce((acc, param) => {
          acc[param] = params[param];
          return acc;
        }, {});
        return acc;
      },
      {}
    );
    console.log(allCardParams);
    return allCardParams;
  }

  let allCardParamsPromise = getAllCardParams();
  let allCardParams;
  let lockedParamsPromise = getLockedParams();
  let lockedParams;
  $: if (allCardParamsPromise && lockedParamsPromise) {
    allCardParamsPromise.then((result) => {
      allCardParams = result;
    });
    lockedParamsPromise.then((result) => {
      lockedParams = result;
    });
  }
</script>

<div id="parameter-div" class={$store.showParameters ? "" : "hide"}>
  {#if allCardParams}
    {#each Object.entries(allCardParams) as [groupName, group]}
      <ParameterCard
        titleParams={groupName}
        cardParams={group}
        {lockedParams}
      />
    {/each}
  {/if}
</div>

<style>
  #parameter-div {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    /* align-items: flex-start; */
    flex-grow: 1;

    transition: all 0.1s ease-in-out;
    border-bottom: 1px solid var(--fg-color);
    margin-left: 15px;
    margin-right: 15px;
    padding-top: 15px;
    padding-bottom: 15px;
  }

  /* Initial state */
  #parameter-div {
    opacity: 1;
    transform: translateX(0);
    height: auto;
    overflow: hidden;
  }

  /* State after button is clicked */
  #parameter-div.hide {
    opacity: 0;
    transform: translateX(-100%);
    height: 0;
    padding: 0;
    border-bottom: none;
  }
</style>
