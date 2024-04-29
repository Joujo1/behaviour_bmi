<script>
  export let value = 0;
  export let tooltip = "ToolTip";
  export let isEnabled = true;
</script>

<div class="setup-ui-button-div">
      <input type="text" bind:value={value} disabled={!isEnabled} title={tooltip}/>
</div>

<style>
  .setup-ui-button-div {
    height: 30px; /* Adjust this value to change the button's height */
    margin: 5px;
    display: flex;
    align-items: center;
  }

  input:disabled {
    color: gray;
  }
  
  input {
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1;
    background-color: var(--bg-color);
    border: 0px solid var(--bg-color);
    border-radius: 4px;
    box-sizing: border-box;
    color: var(--fg-color);
    font-size: 10pt;
    height: 27px;
    width: 50px;
    padding-left: .5em;
    padding-right: .5em;
  }

</style>
