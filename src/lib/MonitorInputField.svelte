<script>
  export let label;
  export let value;
  export let isEnabled;
  export let tooltip;
</script>

<div class="input-label-div">
  <div class="input-ui-label-div">
    <p>{label}</p>
  </div>

  <div class="input-field-div">
    <input type="text" bind:value disabled={!isEnabled} title={tooltip} />
  </div>
</div>

<style>
  .input-label-div {
    height: 25px;
    margin: 5px;
    display: flex;
  }
  .input-ui-label-div {
    min-width: 100px;
    margin-top: 3px;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    font-size: 13pt;
    padding-right: 1em;
    padding-left: 1em;
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
    font-size: 12pt;
    height: 27px;
    width: 60px;
    padding-left: 0.5em;
    padding-right: 0.5em;
  }
</style>
