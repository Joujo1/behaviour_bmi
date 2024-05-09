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
  on:click={onSwitchCallback}
  aria-label="Toggle Color Mode"
  type="button"
  style="width: 57px; height: 27px; background: none; border: none; padding: 0;"
>
  <svg width="57" height="27">
    <rect
      x="0"
      y="2"
      width="55"
      height="24"
      rx="12"
      ry="12"
      fill={$store.inDarkMode
        ? "var(--darkm-bg-color)"
        : "var(--lightm-bg-color)"}
      stroke={$store.inDarkMode
        ? "var(--darkm-fg-color)"
        : "var(--lightm-fg-color)"}
      stroke-width="1"
    />
    <circle
      cx={$store.inDarkMode ? 12 : 55 - 12}
      cy="14"
      r="12"
      fill={$store.inDarkMode
        ? "var(--darkm-fg-color)"
        : "var(--lightm-fg-color)"}
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
