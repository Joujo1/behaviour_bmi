<!-- custom html template compoent that's like a component but focused on visual/html -->
<div class="card">
  <slot name="header">
    <h2>Default header</h2>
  </slot>
  <slot name="content">
    <p>Default content</p>
  </slot>
</div>

<style>
  .card {
    border: 1px solid red;
    padding: 1rem;
    margin: 1rem;
    shape-rendering: 1rem;
  }
</style>
