<script>
  import { portentaData } from "../../store/stores";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer
  title={"Lick Sensor"}
  dataStore={ portentaData }
  wsEndpointName={"portentaoutput"}
  minYData={0}
  maxYData={256}
>
  <div slot="plotarea">
  </div>
</PortentaStreamer>
