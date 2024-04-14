<script>
  export let value = 0;
</script>

<div class="setup-ui-button-div">
      <input type="text" bind:value={value} />
</div>

<style>
  .setup-ui-button-div {
    height: 30px; /* Adjust this value to change the button's height */
    margin: 5px;
  }

  input {
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1;
    background-color: var(--bg-color);
    border: 0px solid var(--bg-color);
    border-radius: 1px;
    box-sizing: border-box;
    color: var(--fg-color);
    font-size: 12pt;
    height: 25px;
    width: 100px;
    padding-left: 1em;
    padding-right: 1em;
  }

</style>
