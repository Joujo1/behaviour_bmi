<script>
  import { ballvelocityData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer

wsEndpointName={"ballvelocity"}
dataStore={ballvelocityData}
minYData={-28}
maxYData={28}
height={180}
title={"Ball Velocity"}
  
nYTicks={3}
yTopOffsetPx={5}
xLeftOffsetPx={90}
>

</PortentaStreamer>