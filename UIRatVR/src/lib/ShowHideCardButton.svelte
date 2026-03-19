<script>
  import { fly } from "svelte/transition";
  export let showCross = true;
  export let onClickCallback;
  export let disabled = false;
</script>

<button
  on:click={onClickCallback}
  aria-label="upload parameters"
  type="button"
  style="width: 32px; height: 27px; background: none; border: none; padding: 0;"
  disabled={disabled}
>
  <svg
    width="6.3479319mm"
    height="5.8799725mm"
    viewBox="0 0 4.7825718 4.3466937"
    version="1.1"
    transform="scale(1.2)"
    id="svg1"
    xmlns="http://www.w3.org/2000/svg"
  >
    <defs id="defs1" />
    <g id="layer1" transform="translate(-79.245192,-61.263818)">
      <g
        id="g54-0"
        transform="matrix(1.0399566,0,0,1.0399566,-718.15759,130.03561)"
        style="fill:#ffffff;fill-opacity:1"
      >
        <rect
          style="fill-opacity:0;fill-rule:evenodd;stroke:var(--fgFaint-color);stroke-width:0.101767;stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1"
          id="rect50-7"
          width="4.5988188"
          height="4.2598009"
          x="766.76544"
          y="-66.181732"
          ry="0.50354564"
        />
        <path
          style="fill:none;fill-opacity:1;fill-rule:evenodd;stroke:{!disabled?"var(--fg-color)":"var(--fgFaint-color)"};stroke-width:0.566222;stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1"
          d="m 768.26848,-64.983601 0.91668,0.87995 0.90469,-0.893401"
          id="path5"
        />
        {#if showCross}
          <path
            transition:fly={{ y: 100, duration: 100 }}
            style="fill:none;fill-opacity:1;fill-rule:evenodd;stroke:var(--fg-color);stroke-width:0.566222;stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1"
            d="m 768.27939,-63.142992 0.89928,-0.945975 0.95299,0.940236"
            id="path7"
          />
        {/if}
      </g>
    </g>
  </svg>
</button>

<style>
  button:hover:enabled {
    cursor: pointer;
  }
  path {
    transition: 0.3s ease;
  }
</style>
