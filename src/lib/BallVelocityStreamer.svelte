<script>
  import { ballvelocityData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer
  title={"Ball Velocity"}
  dataStore={ballvelocityData}
  wsEndpointName={"ballvelocity"}
  minYData={-20}
  maxYData={20}
>
  <div slot="plotarea">
  </div>
</PortentaStreamer>
