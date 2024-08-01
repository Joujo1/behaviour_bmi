<!-- <script>
  import { store } from "../../store/stores";

</script>


<button on:click={() => {$store.showLogfiles = !$store.showLogfiles}}>ShowLogs</button>

 -->


<script>
  import { store } from "../../store/stores";

  // export let lblLeft = ""
  // export let lblRight = ""
  export let onSwitchCallback = () => {
    console.log("no event callback provided");
  };
</script>

<button
  id="colormode-toggle-witch"
  on:click={() => {$store.showLogfiles = !$store.showLogfiles}}
  aria-label="Show Logs"
  type="button"
  style="width: 57px; height: 27px; background: none; border: none; padding: 0;"
>
<svg width="57" height="27" viewBox="0 0 57 27" xmlns="http://www.w3.org/2000/svg">
  <rect
    x="1"
    y="1"
    width="35"
    height="25"
    rx="3"
    ry="3"
    fill={$store.inDarkMode
      ? "var(--darkm-bg-color)"
      : "var(--lightm-bg-color)"}
    stroke={$store.inDarkMode
      ? "var(--darkm-fg-color)"
      : "var(--lightm-fg-color)"}
    stroke-width="1"
  />
  <line
    x1="10"
    y1="8"
    x2="30"
    y2="8"
    stroke={$store.inDarkMode
      ? "var(--darkm-fg-color)"
      : "var(--lightm-fg-color)"}
    stroke-width="2"
  />
  <line
    x1="10"
    y1="14"
    x2="30"
    y2="14"
    stroke={$store.inDarkMode
      ? "var(--darkm-fg-color)"
      : "var(--lightm-fg-color)"}
    stroke-width="2"
  />
  <line
    x1="10"
    y1="20"
    x2="25"
    y2="20"
    stroke={$store.inDarkMode
      ? "var(--darkm-fg-color)"
      : "var(--lightm-fg-color)"}
    stroke-width="2"
  />
</svg>
</button>

<style>
  #colormode-toggle-witch {
    cursor: pointer;
  }
  #colormode-toggle-witch circle {
    transition: ease 0.1s;
  }
</style>
