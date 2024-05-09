<script>
  import { ballvelocityData } from "../../store/stores";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer
  title={"Ball Velocityyy"}
  dataStore={ballvelocityData}
  wsEndpointName={"ballvelocity"}
>
  <div slot="plotarea">
  </div>
</PortentaStreamer>
