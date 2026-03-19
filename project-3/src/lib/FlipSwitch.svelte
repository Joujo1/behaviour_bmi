<script>
    import { store } from "../../store/stores";
    import ToggleSwitch from "./ToggleSwitch.svelte";
  
    export let useNAS;
    export let isEnabled;
  
    function switchDB_NAS() {
      console.log("Switching DB/NAS");
      useNAS = !useNAS;
    }
  </script>
  
  <div id="toggle-switch">
    <p>NAS</p>
    <button
      id="colormode-toggle-witch"
      disabled={!isEnabled}
      on:click={switchDB_NAS}
      aria-label="Toggle Color Mode"
      type="button"
      style="width: 57px; height: 27px; background: none; border: none; padding: 0; margin-top: 5px;"
    >
      <svg width="57" height="27">
        <rect
          x="0"
          y="2"
          width="55"
          height="24"
          rx="12"
          ry="12"
          fill={"var(--bg-color)"} 
          stroke={"var(--fg-color)"}
          stroke-width="1"
        />
        <circle
          cx={useNAS ? 12 : 55 - 12}
          cy="14"
          r="12"
          fill={isEnabled? "var(--fg-color)": "var(--fgFaint-color)"} 
        />
      </svg>
    </button>
    <p>DB</p>
  </div>
  
  <style>
    #toggle-switch {
      display: flex;
      justify-content: space-between;
      align-items: center;
      height: 40px;
    }
  
    p {
      font-size: 12pt;
      color: var(--fg-color);
      padding: 1em;
    }
  
    #colormode-toggle-witch {
      cursor: pointer;
    }
  
    #colormode-toggle-witch circle {
      transition: ease 0.1s;
    }


  </style>