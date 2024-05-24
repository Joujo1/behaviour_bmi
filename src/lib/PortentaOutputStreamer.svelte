<script>
  import { portentaData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer

wsEndpointName={"portentaoutput"}
dataStore={portentaData}
minYData={0.5}
maxYData={4}
height={200}
title={"Portenta Output"}
  
nYTicks={4}
yTickLabels={["Lick", "Reward", "Sound", "Airvalve" ]}
yTopOffsetPx={30}
xLeftOffsetPx={90}
>

</PortentaStreamer>
