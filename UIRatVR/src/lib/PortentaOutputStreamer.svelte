<script>
  import { portentaData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer

wsEndpointName={"portentaoutput"}
dataStore={portentaData}
minYData={0.5}
maxYData={5}
height={145}
title={"Portenta Events"}
  
nYTicks={4}
yTickLabels={["Lick", "Reward", "Sound", "Vacuum", "Airpuff" ]}
yTopOffsetPx={5}
xLeftOffsetPx={90}
>

</PortentaStreamer>
