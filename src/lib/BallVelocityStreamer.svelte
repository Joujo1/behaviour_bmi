<script>
  import { ballvelocityData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer

wsEndpointName={"ballvelocity"}
dataStore={ballvelocityData}
minYData={-30}
maxYData={30}
height={200}
title={"Ball Velocity"}
  
nYTicks={3}
yTopOffsetPx={50}
xLeftOffsetPx={70}
>

</PortentaStreamer>