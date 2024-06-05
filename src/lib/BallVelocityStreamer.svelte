<script>
  import { ballvelocityData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer

wsEndpointName={"ballvelocity"}
dataStore={ballvelocityData}
minYData={-40}
maxYData={40}
height={180}
title={"Ball Velocity"}
  
nYTicks={3}
yTopOffsetPx={50}
xLeftOffsetPx={70}
>

</PortentaStreamer>