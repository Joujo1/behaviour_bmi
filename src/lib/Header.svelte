<script>
  import ColorModeToggle from "./ColorModeToggle.svelte";
  import MenuBar from "./MenuBar.svelte";
</script>

<div id="header-div">
  <div id="logo-div">
    <h1>Virtual Reality Interface</h1>
  </div>
  <div id="menu-div">
    <nav>
      <ul>
        <MenuBar />
      </ul>
    </nav>
  </div>
  <div id="colormode-div">
    <ColorModeToggle />
  </div>
</div>

<style>
  h1 {
    font-weight: lighter;
    font-size: 22pt;
    margin: 0;
    padding: 0;
    color: var(--fg-color);
  }
  #header-div {
    display: flex;
    height: 38px;
    position: sticky;
    background-color: var(--bg-color);
    top: 0;
    z-index: 100;

    border-bottom: 1px solid var(--fg-color);
    margin-left: 15px;
    margin-right: 15px;
    margin-top: 0px;
    margin-bottom: 0px;
    padding-top: 10px;
    padding-bottom: 20px;
  }
  #logo-div {
    flex: 1;
    min-width: 295px;
  }

  #menu-div {
    flex-grow: 1;
    flex: 1;
    justify-content: flex-end;
    display: flex;
  }

  #colormode-div {
    padding-left: 4rem;
    flex-grow: 0;
    align-self: flex-end;
  }
  nav ul {
    display: flex;
    gap: 4rem;
    list-style: none;
    align-self: flex-end;
  }
</style>
