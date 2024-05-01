<script>
  import store from "../../store/store";
  import ParameterCard from "./ParameterCard.svelte";
  import {GETParameters, GETParameterGroups, GETLockedParameters} from "../setup_api.js"

  async function getLockedParams() {
    const lockedParams = await GETLockedParameters();
    return lockedParams;
  }

  async function getAllCardParams() {
    const params = await GETParameters();
    const paramGroups = await GETParameterGroups();

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
    // console.log(allCardParams);
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