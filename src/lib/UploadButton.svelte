<script>
  import store from "../../store/store";
  export let newInput = false;
  export let onClickCallback;

  let uploadBtnCol;
  $: if (newInput) {
    uploadBtnCol = "var(--accent-color)";
    // console.log('newInput', newInput);
  } else {
    uploadBtnCol = "var(--bgFaint-color)";
    // console.log('newInput', newInput);
  }
</script>

<button
  on:click={onClickCallback}
  aria-label="upload parameters"
  type="button"
  disabled={!newInput}
  style="width: 32px; height: 27px; background: none; border: none; padding: 0;"
>
  <svg
    width="8.110507mm"
    height="7.6698022mm"
    viewBox="0 0 6.110507 5.6698022"
    version="1.1"
    id="svg1"
    xmlns="http://www.w3.org/2000/svg"
  >
    <defs id="defs1" />
    <g id="layer1" transform="translate(-78.581249,-60.589581)">
      <g
        id="g54-0"
        transform="matrix(1.0399566,0,0,1.0399566,-718.15759,130.03561)"
        style="fill:#ffffff;fill-opacity:1"
      >
        <rect
          style="fill:{uploadBtnCol};fill-opacity:1;fill-rule:evenodd;stroke:var(--fgFaint-color);stroke-width:0.127209;stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1"
          id="rect50-7"
          width="5.7485237"
          height="5.3247514"
          x="766.19061"
          y="-66.714211"
          ry="0.62943208"
        />
        <path
          d="m 767.06706,-63.791023 v 0.588289 c 0.003,0.452108 0.36914,0.817612 0.82125,0.818897 l 2.35315,0.0071 c 0.45395,2e-6 0.82231,-0.367306 0.82361,-0.82125 v -0.588288"
          id="path51-6"
          style="fill:none;fill-opacity:1;stroke:var(--fgFaint-color);stroke-width:0.407068;stroke-linecap:round;stroke-dasharray:none;stroke-opacity:1"
        />
        <path
          style="fill:none;fill-opacity:1;fill-rule:evenodd;stroke:var(--fgFaint-color);stroke-width:0.407068;stroke-linecap:round;stroke-dasharray:none;stroke-opacity:1"
          d="m 767.98712,-64.652277 1.07359,-1.073584 1.08896,1.07829"
          id="path172"
        />
        <path
          style="fill:var(--fgFaint-color);fill-opacity:1;fill-rule:evenodd;stroke:var(--fgFaint-color);stroke-width:0.407068;stroke-linecap:round;stroke-dasharray:none;stroke-opacity:1"
          d="m 769.06487,-65.565301 v 2.386015"
          id="path173"
        />
      </g>
    </g>
  </svg>
</button>

<style>
  button:hover:enabled {
    cursor: pointer;
  }
</style>
