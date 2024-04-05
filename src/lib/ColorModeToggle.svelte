<script>
  import store from "../../store/store";
  import ToggleSwitch from "./ToggleSwitch.svelte";

  function switchColorMode() {
    $store.inDarkMode = !$store.inDarkMode;

    const colCssVars = [
      "bg-color",
      "bgFaint-color",
      "fg-color",
      "fgFaint-color",
    ];
    const colMode = $store.inDarkMode ? "dark" : "light";

    colCssVars.forEach((colVar) => {
      document.documentElement.style.setProperty(
        "--" + colVar,
        "var(--" + colMode + "m-" + colVar + ")"
      );
    });
    document.documentElement.style.setProperty("color-scheme", colMode);
    document.documentElement.style.setProperty(
      "background-color",
      "var(--bg-color)"
    );
    console.log("Switching color mode");
  }
</script>

<ToggleSwitch onSwitchCallback={switchColorMode} />
