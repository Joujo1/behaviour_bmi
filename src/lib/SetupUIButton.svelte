<script>
  export let label = "";
  export let onClickCallback = {};
  export let stateDependancy = null;
</script>

<div class="setup-ui-button-div">
  <button
    on:click={onClickCallback}
    class={stateDependancy !== null ? "state-button" : "no-state-button"}
  >
    {label}
    {#if stateDependancy !== null}
      <!-- spacer -->
      <svg
        class="overlap-svg"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 30 100"
      ></svg>
      <svg
        class="overlap-svg"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 30 100"
      >
        <rect
          x="0"
          y="0"
          width="30"
          height="100"
          fill={stateDependancy ? "var(--good-color)" : "var(--bgFaint-color)"}
          stroke="var(--bgFaint-color)"
        />
      </svg>
    {/if}
  </button>
</div>

<style>
  .setup-ui-button-div {
    height: 40px; /* Adjust this value to change the button's height */
    margin: 5px;
  }
  .overlap-svg {
    height: 40px;
    border-radius: 5px;
  }

  button {
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1;
    background-color: var(--bg-color);
    border: 0px solid var(--bg-color);
    box-shadow: var(--button-shadow);
    border-radius: 5px;
    box-sizing: border-box;
    color: var(--fg-color);
    cursor: pointer;
    font-size: 12pt;
    height: 40px;
    padding-left: 1em;
  }

  .state-button {
    padding-right: 0em;
  }
  .no-state-button {
    padding-right: 1em;
  }

  button:hover {
    /* box-shadow: 1px 1px 1px 1px rgba(var(--fg-color), 1); */
  }
</style>
