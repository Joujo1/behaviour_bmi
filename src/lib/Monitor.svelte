<script>
  import { store } from "../../store/stores";
  import BallVelocityStreamer from "./BallVelocityStreamer.svelte";
  import PortentaOutputStreamer from "./PortentaOutputStreamer.svelte";
  import SessionInitiation from "./SessionInitiation.svelte";
  import SessionInterference from "./SessionInterference.svelte";
  import ExperimentStateStreamer from "./ExperimentStateStreamer.svelte";
  import Environment from "./Environment.svelte";
  import VideoStreamer from "./VideoStreamer.svelte";

  let testBool = true;
  let currentState = 6;

  // update currentState every 2 seconds to a ranomd int between 0 and 10
  // setInterval(() => {
  //   currentState = Math.floor(Math.random() * 10);
  // }, 2000);

</script>

<div id="monitor-div" class={$store.showMonitor ? "" : "hide"}>
    <SessionInitiation />
    <SessionInterference />
    <BallVelocityStreamer />
    <PortentaOutputStreamer />
    <ExperimentStateStreamer currentState={currentState}/>
    <Environment/>
    <VideoStreamer websocketName="bodycam" title="Overview Camera"/>
    <VideoStreamer websocketName="facecam" title="Face Camera"/>
    <VideoStreamer websocketName="unitycam" title="Unity View"/>
</div>

<!-- 
    
@app.websocket("/stream/bodycam")
async def stream_unityoutput(websocket: WebSocket):
    validate_state(app.state.state, valid_initiated=True, 
                   valid_shm_created={P.SHM_NAME_BODY_CAM: True},
                   valid_proc_running={"bodycam2shm": True,})
    
    L = Logger()
    frame_shm = VideoFrameSHMInterface(shm_struct_fname(P.SHM_NAME_BODY_CAM))
    
    await websocket.accept()
    
    prv_frame_package = b''
    try:
        t0 = time.time()                
        while True:
            await asyncio.sleep(0.01) # check memory every 10ms
            
            # wait until new frame is available
            if (frame_package := frame_shm.get_package()) == prv_frame_package:
                continue
            prv_frame_package = frame_package

            frame = frame_shm.get_frame()
            L.logger.debug(f"New frame {frame.shape} read from SHM: {frame_package}")
            
            frame_encoded = cv2.imencode('.jpg', frame)[1].tobytes()  # Encode the frame as JPEG
            await websocket.send_bytes(frame_encoded)  # Send the encoded frame
    except:
        pass
    finally:
        # frame_shm.close_shm()
        websocket.close()

@app.websocket("/stream/facecam")
async def stream_unityoutput(websocket: WebSocket):
    validate_state(app.state.state, valid_initiated=True, 
                   valid_shm_created={P.SHM_NAME_FACE_CAM: True},
                   valid_proc_running={"facecam2shm": True,})
    
    L = Logger()
    frame_shm = VideoFrameSHMInterface(shm_struct_fname(P.SHM_NAME_FACE_CAM))
    
    await websocket.accept()
    
    prv_frame_package = b''
    try:
        t0 = time.time()                
        while True:
            await asyncio.sleep(0.01) # check memory every 10ms
            
            # wait until new frame is available
            if (frame_package := frame_shm.get_package()) == prv_frame_package:
                continue
            prv_frame_package = frame_package

            frame = frame_shm.get_frame()
            L.logger.debug(f"New frame {frame.shape} read from SHM: {frame_package}")
            
            frame_encoded = cv2.imencode('.jpg', frame)[1].tobytes()  # Encode the frame as JPEG
            await websocket.send_bytes(frame_encoded)  # Send the encoded frame
    except:
        pass
    finally:
        # frame_shm.close_shm()
        websocket.close()

@app.websocket("/stream/unitycam")
async def stream_unityoutput(websocket: WebSocket):
    validate_state(app.state.state, valid_initiated=True, 
                   valid_shm_created={P.SHM_NAME_UNITY_CAM: True},
                   valid_proc_running={"unity": True,})
    
    L = Logger()
    frame_shm = VideoFrameSHMInterface(shm_struct_fname(P.SHM_NAME_UNITY_CAM))
    
    await websocket.accept()
    
    prv_frame_package = b''
    try:
        t0 = time.time()                
        while True:
            await asyncio.sleep(0.01) # check memory every 10ms
            
            # wait until new frame is available
            if (frame_package := frame_shm.get_package()) == prv_frame_package:
                continue
            prv_frame_package = frame_package

            frame = frame_shm.get_frame()
            L.logger.debug(f"New frame {frame.shape} read from SHM: {frame_package}")
            
            frame_encoded = cv2.imencode('.jpg', frame)[1].tobytes()  # Encode the frame as JPEG
            await websocket.send_bytes(frame_encoded)  # Send the encoded frame
    except:
        pass
    finally:
        # frame_shm.close_shm()
        websocket.close() -->