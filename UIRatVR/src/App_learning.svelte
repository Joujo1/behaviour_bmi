
<script>
  import Child from './lib/Child.svelte'
  import Card from './lib/Card.svelte'
  import store from '../store/store';

  // all of you are stateful variables
  let name = 'Simon';
  let age = 12;
  let ageMsg;
  let interable = [{value: 'item1string', isDone: false}, {value: 'othersting2', isDone: true}]
  let job = "homeless"

  const increaseAge = () => {
    age += 1;
  }

  // Derived state
  $: uppercase = name.toUpperCase();
  $: if (age > 18) {
    ageMsg = 'You are an adult!'
  } else {
    ageMsg = 'You are a minor!'
  }

</script>

<main>
  <h1>Hello {uppercase}!, {$store.job}</h1>
  <p>You are {age} years old.</p>
  <p>{ageMsg}</p>
  <!-- bind and on are two-way binding and event listeners in svelte -->
  <button on:click={increaseAge} disabled={false}>🎂🎉🎈</button>
  <input bind:value={name} placeholder="Enter your name" />

  {#if name === 'Simon'}
    <p>You rock!</p>
  {:else}
    <p>Who are you?</p>
  {/if}

  {#each interable as item, index}
  <p class={item.isDone ? "doneItem": "undoneItem"}>{index+1}: {item.value}</p> 
  {/each}
  <Child job={job}/>
  <Child job="child12"/>
  <Child />
  <Card>
    <div slot="header">
      <h1>This is a header</h1>
    </div>
    <p slot="content">This is a content</p>
  </Card>
</main>

<style>
  h1 {
    color: #ff3e00;
  }

  .doneItem {
    text-decoration: line-through;
  }
  .undoneItem {
    color: red;
  }


</style>
