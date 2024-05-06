<script>
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import PortentaStreamer from "./PortentaStreamer.svelte";
</script>

<PortentaStreamer
  title={"Ball Velocity"}
  wsOnMessageCallback={(msg) => {console.debug(JSON.parse(msg.data))}}
  wsEndpointName={"ballvelocity"}
>
  <div slot="plotarea">
  </div>
</PortentaStreamer>
