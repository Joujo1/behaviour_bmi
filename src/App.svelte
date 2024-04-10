<script>
    import Header from "./lib/Header.svelte";
    import store from "../store/store";
    import Parameters from "./lib/Parameters.svelte";
    import Setup from "./lib/Setup.svelte";
    import Modal from "./lib/Modal.svelte";
</script>

<main class={$store.inDarkMode ? "darkm" : "lightm"}>
    <Header />
    {#if $store.showModal}
        <Modal/>
    {/if}
    <Parameters />
    <Setup />
    <!-- Your content here -->
</main>

<style>
    main {
        min-width: 1000px; /* Replace with the minimum width you want */
    }
</style>