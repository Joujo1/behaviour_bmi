<script>
  export let label;
  export let value;
  export let isEnabled = true;
  export let options = [];
  export let getOptions = () => {};
</script>

<div class="dropdown-ui-div">
  <div class="dropdown-ui-label-div">
    <p>{label}</p>
  </div>

  <select
    bind:value
    on:click={getOptions}
    disabled={!isEnabled}
    title={value}
    style="color: {isEnabled ? 'var(--fg-color)' : 'gray'}"
  >
    <option value="">Select</option>
    {#each options as option}
      <option value={option}>{option}</option>
    {/each}
  </select>
</div>

<style>
  .dropdown-ui-div {
    height: 25px;
    margin: 5px;
    display: flex;
    /* max-width: 200px; */

  }
  .dropdown-ui-label-div {
    min-width: 100px;
    margin-top: 3px;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    font-size: 13pt;
    padding-right: 1em;
    padding-left: 1em;
  }
  select {
    font-size: 12pt;
    height: 25px;
    border-radius: 4px;
    border: 1px solid var(--bg-color);
    background-color: var(--bg-color);
    color: var(--fg-color);
    width: 120px;
    /* width: 84px; */
  }
</style>
