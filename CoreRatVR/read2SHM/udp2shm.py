import sys
import os
import socket
import time
import argparse

# When executed as a process, add parent SHM dir to path again
sys.path.insert(1, os.path.join(sys.path[0], '..')) # project dir
sys.path.insert(1, os.path.join(sys.path[0], '..', 'SHM')) # SHM dir

from CyclicPackagesSHMInterface import CyclicPackagesSHMInterface
from FlagSHMInterface import FlagSHMInterface
from CustomLogger import CustomLogger as Logger
from udp_processor import DataProcessor
from udp_receiver import UDPreceiver

def _read_udpstream(frame_shm, termflag_shm, paradigmflag_shm, local_port):
    L = Logger()
    L.logger.info(f"Listening to UDP stream on port {local_port} & writing to SHM...")

    pi_ip_map = {
        5001: "192.168.1.101", 5002: "192.168.1.102", 5003: "192.168.1.103",
        5004: "192.168.1.104", 5005: "192.168.1.105", 5006: "192.168.1.106",
        5007: "192.168.1.107", 5008: "192.168.1.108", 5009: "192.168.1.109",
        5010: "192.168.1.110", 5011: "192.168.1.111", 5012: "192.168.1.112"
    }
    
    pi_ip = pi_ip_map.get(local_port)
    PI_CMD_PORT = 5006
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    frame_i = 0
    prv_t = 0

    def frame_acqu_callback(data, sender_info):
        nonlocal frame_i
        nonlocal prv_t
        image = data.get('frame')
        if image is None:
            return

        t = int(time.time()*1e6)
        pack = "<{" + f"N:I,ID:{frame_i},PCT:{t}" + "}>\r\n"
        
        x_res = frame_shm.metadata['x_resolution']
        y_res = frame_shm.metadata['y_resolution']
        image = image[:y_res, :x_res]
        image = image[::-1, ::-1] 

        frame_bytes = image.tobytes()
        package_nbytes = frame_shm.metadata['frame_package_nbytes']
        
        combined_bytes = bytearray(package_nbytes + len(frame_bytes))
        combined_bytes[:len(pack)] = pack.encode('utf-8')
        combined_bytes[package_nbytes:] = frame_bytes

        frame_shm.push(combined_bytes)
        
        frame_i += 1
        prv_t = t

    processor = DataProcessor(callback_func=frame_acqu_callback)
    receiver = UDPreceiver(local_port=local_port, data_callback=processor.parse_dispatch_packet)
    receiver.start()
    
    if pi_ip:
        try:
            cmd_sock.sendto(b"START_STREAMING", (pi_ip, PI_CMD_PORT))
            L.logger.info(f"Sent START command to Pi at {pi_ip}:{PI_CMD_PORT}")
        except Exception as e:
            L.logger.error(f"Failed to send command to Pi: {e}")

    paradigm_running_state = paradigmflag_shm.is_set()

    try:
        while True:
            if termflag_shm.is_set():
                L.logger.info("Termination flag raised by UI. Shutting down...")
                break

            if paradigmflag_shm.is_set() != paradigm_running_state:
                new_state = paradigmflag_shm.is_set()
                L.logger.info(f"UI Paradigm state changed to: {new_state}")
                paradigm_running_state = new_state
                
            time.sleep(0.1)
            
    finally:
        if pi_ip:
            try:
                cmd_sock.sendto(b"STOP_STREAMING", (pi_ip, PI_CMD_PORT))
                L.logger.info(f"Sent STOP command to Pi at {pi_ip}:{PI_CMD_PORT}")
            except Exception:
                pass
                
        cmd_sock.close()
        receiver.stop()

def run_udp2shm(videoframe_shm_struc_fname, termflag_shm_struc_fname, 
                paradigmflag_shm_struc_fname, cam_name,
                x_topleft, y_topleft, local_port):
    
    frame_shm = CyclicPackagesSHMInterface(videoframe_shm_struc_fname)
    termflag_shm = FlagSHMInterface(termflag_shm_struc_fname)
    paradigmflag_shm = FlagSHMInterface(paradigmflag_shm_struc_fname)
    
    _read_udpstream(frame_shm, termflag_shm, paradigmflag_shm, local_port)

if __name__ == "__main__":
    argParser = argparse.ArgumentParser(description="Read UDP camera stream and place in SHM")
    argParser.add_argument("--videoframe_shm_struc_fname", required=True)
    argParser.add_argument("--termflag_shm_struc_fname", required=True)
    argParser.add_argument("--paradigmflag_shm_struc_fname", required=True)
    argParser.add_argument("--logging_dir", required=True)
    argParser.add_argument("--logging_name", required=True)
    argParser.add_argument("--logging_level", required=True)
    argParser.add_argument("--cam_name", required=True)
    argParser.add_argument("--x_topleft", type=int, default=0)
    argParser.add_argument("--y_topleft", type=int, default=0)
    argParser.add_argument("--process_prio", type=int, default=-1)
    argParser.add_argument("--local_port", type=int, required=True)
    
    kwargs = vars(argParser.parse_args())
    
    L = Logger()
    L.init_logger(kwargs.pop('logging_name'), kwargs.pop("logging_dir"), 
                  kwargs.pop("logging_level"))
    L.logger.info("Subprocess started")
    L.logger.debug(L.fmtmsg(kwargs))
    
    if sys.platform.startswith('linux'):
        if (prio := kwargs.pop("process_prio")) != -1:
            os.system(f'sudo chrt -f -p {prio} {os.getpid()}')
            
    run_udp2shm(**kwargs)