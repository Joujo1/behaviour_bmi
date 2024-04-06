<script>
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  export let message = '';

  function close() {
    dispatch('close');
  }
</script>

<div class="modal">
  <div class="modal-content">
    <span class="close-button" on:click={close}>X</span>
    <p>{message}</p>
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