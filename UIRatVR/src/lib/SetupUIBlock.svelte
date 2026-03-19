<script>
</script>
  
  <div class="setup-ui-block-div">
    <div class="setup-ui-header-div">
        <h1>
            <slot name="header"></slot>
        </h1>
    </div>
    <slot name="setupui"></slot>
  </div>
<style>
    .setup-ui-block-div {
      background-color: var(--bgFaint-color);
      padding: 15px;
      padding-bottom: 10px;
      border-radius: 7px;
      margin: 15px;
      min-width: 450px;
    }
    .setup-ui-header-div {
      border-bottom: 1px solid var(--fg-color);
      padding-bottom: 12px;
      margin-bottom: 10px;
    }
    .setup-ui-header-div h1 {
      font-weight: bold;
      font-size: 14pt;
      margin: 0;
      padding: 0;
      color: var(--fg-color);
    }
</style>