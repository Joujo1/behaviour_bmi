<script>
  // import { createEventDispatcher } from 'svelte';
  import { store } from "../../store/stores";

  // const dispatch = createEventDispatcher();

  function close() {
    // dispatch('close');
    $store.showModal = false;
    $store.modalMessage = "";
  }
</script>

<div class="modal">
  <div class="modal-content">
    <button
      class="close-button"
      on:click={close}
      aria-label="Close"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="feather feather-x"
      >
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    </button>
    <p>{$store.modalMessage}</p>
  </div>
</div>

<style>
  .modal {
    position: fixed;
    z-index: 1;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    overflow: auto;
    opacity: 95%;
    background-color: var(--bg-color);
  }

  .modal-content {
    background-color: var(--bgFaint-color);
    margin: 15% auto;
    padding: 20px;
    border: 2px solid var(--error-color);
    width: 50%;
    opacity: 100%;
    border-radius: 10px;
    font-size: larger;
  }

  .close-button {
    color: var(--fg-color);
    float: right;
    font-size: 28px;
    font-weight: bold;
  }

  .close-button:hover,
  .close-button:focus {
    color: var(--fg-color);
    text-decoration: none;
    cursor: pointer;
  }
</style>
