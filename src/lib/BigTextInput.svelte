<script>
  export let value = "";
  export let isEnabled = true;
</script>

<div class="big-text-input-div">
      <textarea bind:value={value} disabled={!isEnabled}/>
</div>

<style>
  .big-text-input-div {
    height: 100px; /* Adjust this value to change the button's height */
    width: 128px; 
    margin: 5px;
    display: flex;
    align-items: center;
    margin-left: 40px
  }

  textarea:disabled {
    color: gray;
  }
  
  textarea {
    height: 100px; 
    /* width: 180px; Adjust this value to change the button's height */
    /* display: flex; */
    /* justify-content: center; */
    /* align-items: center; */
    z-index: 1;
    background-color: var(--bg-color);
    border: 0px solid var(--bg-color);
    border-radius: 4px;
    box-sizing: border-box;
    color: var(--fg-color);
    font-size: 8pt;
    padding-left: .5em;
    padding-right: .5em;
    resize: none;
  }

</style>
