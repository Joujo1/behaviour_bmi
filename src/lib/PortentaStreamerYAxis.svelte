<script>
    export let height;
    // export let width;
    export let tickLength;
    export let xLeftOffsetPx;

    export let yTopOffsetPx;
    export let yBottomOffsetPx;
    export let yAxisOffsetPx;
        
    export let yTicks;
</script>


<!-- Y Axis -->
<!-- Y label: [a.u.] -->
<text
    x={xLeftOffsetPx - tickLength - yAxisOffsetPx - 7}
    y={yTopOffsetPx - 30}
    font-size={18}
    text-anchor="end"
    fill="var(--fg-color)"
    dominant-baseline="middle"
>
    {"[a.u.]"}</text
>
<!-- y axis line -->
<line
    x1={xLeftOffsetPx - yAxisOffsetPx}
    y1={yTopOffsetPx}
    x2={xLeftOffsetPx - yAxisOffsetPx}
    y2={height - yBottomOffsetPx}
    stroke-width="1"
    stroke="var(--fgFaint-color)"
/>
{#each yTicks as { value, position }}
    <!-- y axis ticks -->
    <line
    x1={xLeftOffsetPx - yAxisOffsetPx}
    y1={position}
    x2={xLeftOffsetPx - tickLength - yAxisOffsetPx}
    y2={position}
    stroke="var(--fgFaint-color)"
    />

    <!-- y axis tick labels -->
    <text
    x={xLeftOffsetPx - tickLength - yAxisOffsetPx - 7}
    y={position}
    text-anchor="end"
    dominant-baseline="middle"
    fill="var(--fg-color)">{value}</text
    >
{/each}