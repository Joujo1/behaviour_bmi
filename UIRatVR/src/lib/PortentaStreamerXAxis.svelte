
<script>
    export let height;
    export let width;
    export let tickLength;
    export let xLeftOffsetPx;

    // export let yTopOffsetPx;
    export let yBottomOffsetPx;
    export let yAxisOffsetPx;
    
    export let xTicks;
</script>

<svg>

<!-- X Axis -->
<!-- main axis line -->
<line
    x1={xLeftOffsetPx}
    y1={height - yBottomOffsetPx}
    x2={width}
    y2={height - yBottomOffsetPx}
    stroke-width="1"
    stroke="var(--fgFaint-color)"
/>
{#each xTicks as { value, position }}
    <!-- x ticks -->
    <line
    x1={position}
    y1={height - yBottomOffsetPx}
    x2={position}
    y2={height - yBottomOffsetPx + tickLength}
    stroke-width="1"
    stroke="var(--fgFaint-color)"
    />
    <!-- x tick labels -->
    <text
    x={position}
    y={height - yBottomOffsetPx + tickLength + 17}
    fill="var(--fg-color)"
    text-anchor="middle">{(value / 1e6).toLocaleString()}</text
    >
{/each}

<!-- x label background box: [s] -->
<rect
    x={xLeftOffsetPx - yAxisOffsetPx - 15}
    y={height - yBottomOffsetPx + 1}
    width={60}
    height={30}
    fill="var(--bg-color)"
/>
<!-- x label: [s] -->
<text
    x={xLeftOffsetPx}
    y={height - yBottomOffsetPx + tickLength + 17}
    font-size={18}
    fill="var(--fg-color)"
    text-anchor="middle">
{"[s]"}</text>

</svg>
