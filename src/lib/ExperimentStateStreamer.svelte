<script>
  import { onMount } from "svelte";
  import { store } from "../../store/stores";
  import { select, drag, line, transition, easeBounce } from "d3";
  import ShowHideCardButton from "./ShowHideCardButton.svelte";
  import { GETParadigmsFSMs } from "../monitor_api.js";
  import { openWebsocket } from "../monitor_api.js";

  // websocket stuff
  let closeCallback = () => {};
  const wsEndpointName = "unityoutput";

  // reactive elements (circles is a d3.selection)
  let svg;
  let circles;

  // visual properties
  let isActive = false;
  let title = "Experiment";
  let width = 0;
  let height = 0;
  let DOMRect = { width: width, height: height};
  const nodeRadius = 50;

  // nodes and edges
  var stateData = []; 
  var transitionData = [];

  // unity state at current frame
  let currentState;


  $: if (DOMRect) {
    width = DOMRect.width;
    height = DOMRect.width;
  }

  $: if (circles) {
    circles
      .style("stroke", (d) =>
        d.stateID === currentState ? "var(--accent-color)" : "var(--fg-color)"
      )
      .style("stroke-width", (d) =>
        d.stateID === currentState ? 4 : 1
      );
  }

  function nodeLocations2Cache() {
    var nodeLocations = {};
    var paradigmID;
    stateData.forEach((d) => {
      paradigmID = d.paradigmID;
      nodeLocations[d.guid] = { cx: d.cx, cy: d.cy };
    });
    // save this object to local storage
    localStorage.setItem(
      "P" + paradigmID + "_nodeLocs",
      JSON.stringify(nodeLocations)
    );
  }

  function handleWSHandshakeError(result) {
    console.log("in handleWSHandshakeError");
    closeCallback();
    isActive = false;
    $store.showModal = true;
    $store.modalMessage = "Websocket failed to open. Check server for deatils.";
  }

  function wsOnMessageCallback(msg) {
    let newData = JSON.parse(msg.data);
    console.log(newData);
    currentState = newData[0].S;
  }

  async function switchCardOnOff(event) {
    if (!isActive) {
      let data = await GETParadigmsFSMs();
      console.log(data);
      // check if data is a string (implecitly means an error message)
      if (typeof data === "string") {
        $store.showModal = true;
        $store.modalMessage = data;
        closeCallback();
        return;
      } else {
        isActive = !isActive;
        loadStateTransitionData(data);
        setupExperimtentStateStreamer();
        closeCallback = openWebsocket(
          wsEndpointName,
          wsOnMessageCallback,
          handleWSHandshakeError
        );
      }
    } else {
      isActive = !isActive;
      // save the node locaions (cx,cy) to locatStorga
      nodeLocations2Cache();
      title = "Experiment";
      select(svg).selectAll("*").remove();
      stateData = [];
      transitionData = [];
    }
  }

  // loads the static setup of nodes and edges 
  // populates stateData and transitionData
  function loadStateTransitionData(data) {
    const numStates = Object.entries(data.states).length;

    const assignInitalNodeLocation = (guid, paradigm, i) => {
      const cachedLocsKey = "P" + paradigm + "_nodeLocs";
      if (cachedLocsKey in localStorage) {
        var nodeLocs = JSON.parse(
          localStorage.getItem("P" + paradigm + "_nodeLocs")
        );
        if (guid in nodeLocs) {
          return [nodeLocs[guid].cx, nodeLocs[guid].cy];
        }
      } else {
        console.log("No cached locations found for paradigm: ", paradigm);
        const angle = (i / numStates) * 2 * Math.PI;
        const initialLocationRadius = 200;
        const cx = width / 2 + initialLocationRadius * Math.cos(angle);
        const cy = height / 2 + initialLocationRadius * Math.sin(angle);
        return [cx, cy];
      }
    };
    
    // ====== LOAD STATES AS NODES ======
    stateData = Object.entries(data.states).map(([key, value], i) => {
      // update title to paradigm name when base state found
      if (value.name[0] == "P") title = title + ": " + value.name.split("_")[1];
      const [cx, cy] = assignInitalNodeLocation(key, value.paradigm, i);

      // for annotation
      var actionsStr = "";
      if ("actions_guids" in value) {
        const actions = value.actions_guids.map((actionGUID) => {
          return data.actions[actionGUID].name;
        });
        actionsStr = "Actions:\n\t" + actions.join("\n\t");
      }
      return {
        cx: cx,
        cy: cy,
        stateID: value.stateID,
        label: value.name.split("_")[1],
        paradigmID: value.paradigm,
        guid: key,
        r: nodeRadius,
        tooltip:
          `${value.name} from ${value.path}\n` +
          `stateID: ${value.stateID}\n${actionsStr}`,
      };
    });
    console.log("stateData: ", stateData);

    // ====== LOAD TRANSITIONS AS EDGES ======
    Object.entries(data.states).map(([stateGUID, value], i) => {
      var sourceState = stateData.filter((d) => d.guid == stateGUID)[0];

      // iteraate over all transitions of this state
      value.transitions_guids.forEach((transitionGUID) => {
        var transition = data.transitions[transitionGUID];
        // console.log("transition: ", transition);
        var trTrueState = transition.truestate;
        // console.log("trTrueState: ", trTrueState);
        var decision = data.decisions[transition.decision];
        // console.log("decision: ", decision);

        var edge = {
          source: sourceState,
          target: stateData.filter((d) => d.guid == transition.truestate)[0],
          // transitionName: transition.name,
          // decisionDirection: true,
          // decisionName: decision.name,
          tooltip:
            `${transition.name} from ${decision.path}\n` +
            `${decision.name}\n${decision.switchDescription}`,
        };
        // console.log("edge: ", edge);
        transitionData.push(edge);

        // console.log("False state: ", transition.falsestate);
        var falseTarget = stateData.filter(
          (d) => d.guid == transition.falsestate
        )[0];
        // RemainInState (see GUID below) is often the false state - ignored here
        if (
          falseTarget &&
          falseTarget.name != "da5de4176efc130acbcbc8a7513855ee"
        ) {
          var edgeFalse = {
            source: sourceState,
            target: falseTarget,
            tooltip:
              `${transition.name} from ${decision.path}\n` +
              `${decision.name}\nNOT ${decision.switchDescription}`,
          };
          // console.log("False edge: ", edgeFalse);
          transitionData.push(edgeFalse);
        }
      });
      // console.log("----------------------");
    });
    console.log("transtitionData: ", transitionData);
  }

  // non reactive d3 function handling dragging of nodes
  function setupExperimtentStateStreamer() {
    // first append the nodes 
    circles = select(svg)
      .selectAll("circle")
      .data(stateData)
      .enter()
      .append("circle")
      .attr("cx", (d) => d.cx)
      .attr("cy", (d) => d.cy)
      .attr("r", (d) => d.r)
      .attr("class", "draggable")
      .attr("stateID", (d) => d.stateID)
      .style("fill", "var(--bg-color)")
      .style("stroke", "var(--fg-color)");
    // on hover
    circles.append("title").text((d) => d.tooltip);

    // add the labels to the nodes
    const labels = select(svg)
      .selectAll("text")
      .data(stateData)
      .enter()
      .append("text")
      .attr("x", (d) => d.cx)
      .attr("y", (d) => d.cy)
      .text((d) => d.label)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .style("fill", "var(--fg-color)")
      .style("pointer-events", "none")
      .style("user-select", "none");

    // define the arrowhead
    select(svg)
      .append("defs")
      .append("marker")
      .attr("id", "arrowhead")
      .attr("viewBox", "-0 -5 10 10")
      .attr("refX", 5)
      .attr("refY", 0)
      .attr("orient", "auto")
      .attr("markerWidth", 9)
      .attr("markerHeight", 9)
      .attr("xoverflow", "visible")
      .append("svg:path")
      .attr("d", "M 0,-5 L 10 ,0 L 0,5")
      .attr("fill", "var(--fg-color)")
      .style("stroke", "none");

    const lineGenerator = line()
      .x((d) => d.cx)
      .y((d) => d.cy);

    // shorten the edge by the node radius
    const adjustEdgeEndpoints = (d) => {
      const dx = d.target.cx - d.source.cx;
      const dy = d.target.cy - d.source.cy;
      const angle = Math.atan2(dy, dx);
      const radius = d.source.r;

      return [
        {
          cx: d.source.cx + radius * Math.cos(angle),
          cy: d.source.cy + radius * Math.sin(angle),
          r: radius,
        },
        {
          cx: d.target.cx - radius * Math.cos(angle),
          cy: d.target.cy - radius * Math.sin(angle),
          r: radius,
        },
      ];
    };

    // append the edges
    const edges = select(svg)
      .selectAll("path")
      .data(transitionData)
      .enter()
      .append("path")
      .attr("stroke", "var(--fg-color)")
      .attr("fill", "none")
      .attr("marker-end", "url(#arrowhead)")
      .attr("stroke-width", 2)
      .attr("d", (d) => lineGenerator(adjustEdgeEndpoints(d)));
    // on hover
    edges.append("title").text((d) => d.tooltip);

    const dragBehavior = drag()
      .on("start", function (event, d) {
        select(this).attr("stroke-width", 2);
      })
      .on("drag", function (event, d) {
        select(this)
          .transition()
          .duration(50)
          .ease(easeBounce)
          .attr("cx", (d.cx = event.x))
          .attr("cy", (d.cy = event.y));
        labels.each(function (labelData) {
          if (labelData === d) {
            select(this).attr("x", d.cx).attr("y", d.cy);
          }
        });
        // Update edges dynamically
        edges.attr("d", (d) => lineGenerator(adjustEdgeEndpoints(d)));
      })
      .on("end", function (event, d) {
        select(this).attr("stroke-width", 1);
      });

    circles.call(dragBehavior);
  }
</script>

<div class="portenta-stream-card">
  <div id="card-header-div">
    <div>
      <h1>{title}</h1>
    </div>
    <div id="swtich-btn-div">
      <ShowHideCardButton
        onClickCallback={switchCardOnOff}
        showCross={isActive}
      />
    </div>
  </div>
  <div
    class="experiment-fsm-div"
    bind:contentRect={DOMRect}
    style="height: {isActive ? height : 0}px"
  >
    <svg bind:this={svg} {width} {height}></svg>
  </div>
</div>

<style>
  .portenta-stream-card {
    border: 1px solid var(--bgFaint-color);
    padding: 15px;
    border-radius: 7px;
    margin: 15px;
    flex-grow: 1;
    max-width: 600px; 
    min-width: 300px; 
  }
  #card-header-div {
    border-bottom: 1px solid var(--fgFaint-color);
    padding-bottom: 6px;
    display: flex;
  }
  #card-header-div h1 {
    font-weight: bold;
    font-size: 14pt;
    margin: 0;
    padding: 0;
    color: var(--fg-color);
  }
  #swtich-btn-div {
    flex-grow: 1;
    display: flex;
    justify-content: flex-end;
  }
</style>
