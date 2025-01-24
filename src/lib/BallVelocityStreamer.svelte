<script>
  import { ballvelocityData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer

wsEndpointName={"ballvelocity"}
dataStore={ballvelocityData}
minYData={-3.5}
maxYData={3.5}
height={180}
title={"Ball Velocity"}
  
nYTicks={3}
yTopOffsetPx={5}
xLeftOffsetPx={90}
>

</PortentaStreamer>