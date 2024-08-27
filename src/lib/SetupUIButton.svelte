<script>
  export let label = "";
  export let onClickCallback = {};
  export let stateDependancy = null;
  export let warningsStateDependancy = null;
  export let errorsStateDependancy = null;
  export let isEnabled = true;
  export let background_color = "var(--bg-color)";
</script>

<div class="setup-ui-button-div">
  <button
    on:click={onClickCallback}
    disabled={!isEnabled}
    class={stateDependancy !== null ? "state-button" : "no-state-button"}
    style={"background-color: " + background_color}
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
        <rect
          x="0"
          y="20"
          width="60"
          height="20"
          fill={warningsStateDependancy ? "var(--accent-color)" : "none"}
          />
        {#if warningsStateDependancy}
          <title>{warningsStateDependancy} Warnings</title>
        {/if}

        <rect
          x="0"
          y="40"
          width="60"
          height="20"
          fill={errorsStateDependancy ? "var(--error-color)" : "none"}
        />
        {#if errorsStateDependancy}
          <title>{errorsStateDependancy} Errors</title>
        {/if}
      </svg>
    {/if}
  </button>
</div>

<style>
  .setup-ui-button-div {
    height: 30px; /* Adjust this value to change the button's height */
    margin: 5px;
  }
  .overlap-svg {
    height: 35px;
    border-radius: 5px;
  }

  button {
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1;
    /* background-color: var(--bg-color); */
    border: 0px solid var(--bg-color);
    box-shadow: var(--button-shadow);
    border-radius: 5px;
    box-sizing: border-box;
    color: var(--fg-color);
    cursor: pointer;
    font-size: 12pt;
    font-family: Futura, Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;;
    height: 35px;
    padding-left: 1em;
  }
  button:disabled {
    /* background-color: var(--bgFaint-color); */
    color: gray;
    cursor: default;
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