import time
import threading
from enum import Enum

class TrialState(Enum):
    WAIT_FOR_TRIAL_START = 0
    WAIT_FOR_CPOKE = 1
    CPOKE_IN = 2
    CLICKS_ON = 3
    STIMULATION = 4
    WAIT_FOR_SPOKE = 5
    LEFT_REWARD = 6
    RIGHT_REWARD = 7
    ERROR = 8
    TRIAL_END = 10

class TrialStateMachine:
    def __init__(self, gpio_controller, audio_controller, trial_params):
        self.gpio = gpio_controller
        self.audio = audio_controller
        self.params = trial_params

        self.current_state = TrialState.WAIT_FOR_TRIAL_START
        self.state_start_time = 0.0
        self.trial_start_time = 0.0
        self.running = False
        self.completed = False

        self.master_trial_log = []
        self.frame_event_buffer = []

        self.buffer_lock = threading.Lock()

        self.state_timings = trial_params.get('states', {})
        self.click_times_left = trial_params.get('clickTimesL', [])
        self.click_times_right = trial_params.get('clickTimesR', [])
        self.reward_side = trial_params.get('side', 'L')
        self.task_type = trial_params.get('task', 'simpleConditioning')
        self.central_poke_required_time = trial_params.get('centralPokeTime', 0.5)

        # Trial outcome tracking
        self.violated = False  # Whether rat prematurely ended nose fixation
        self.responded = False  # Whether animal entered side port
        self.response_time_s = None  # Time from cpoke_out to spoke
        self.cpoke_out_time = None  # Time when animal removed nose from fixation
        self.cpoke_req_end_time = None  # Time when animal was allowed to remove nose
        self.choice = None  # 'L', 'R', or None

        self.audio_completed = False
        self.reward_delivered = False

    def log_event(self, event_type, data = None):
        timestamp = time.time() - self.trial_start_time if self.trial_start_time > 0 else 0.0
        log_entry = {
            't': round(timestamp, 4),           
            'e': event_type,                    
            's': self.current_state.value,
            'd': data or {}                     
        }
        self.master_trial_log.append(log_entry)

        with self.buffer_lock:
            self.frame_event_buffer.append(log_entry)

    def pop_frame_events(self):
        """
        Called by the Camera thread
        """
        with self.buffer_lock:
            events = self.frame_event_buffer.copy()
            self.frame_event_buffer.clear()
        return events
    
    def start(self):
        self.running = True
        self.trial_start_time = time.time()
        self.state_start_time = self.trial_start_time
        self.current_state = TrialState.WAIT_FOR_TRIAL_START
        
        self.gpio.led_center_on()
        
        self.log_event('trial_start', {'params': self.params})
        
        # Start the click scheduler
        self.click_thread = threading.Thread(target=self._click_scheduler, daemon=True)
        self.click_thread.start()
        
        print(f"Trial started - Task: {self.task_type}, Reward side: {self.reward_side}")
    

    def stop(self):
        self.running = False
        self.gpio.cleanup_trial()
        self.log_event('TRIAL_STOPPED')
        print("Trial stopped")
        

    def _end_trial(self):
        self.completed = True
        self.running = False
        trial_duration = time.time() - self.trial_start_time
        
        self.log_event('trial_end', {'duration': trial_duration})
        self.gpio.cleanup_trial()
        print(f"Trial completed in {trial_duration:.2f}s")

    
    def update(self):
        if not self.running or self.completed:
            return False
        
        current_time = time.time()
        time_in_state = current_time - self.state_start_time
        
        #Timeout check
        max_time = self.state_timings.get(self.current_state.value)
        if max_time is not None and time_in_state > max_time:
            self._handle_state_timeout()
            return True
        
        #State logic
        if self.current_state == TrialState.WAIT_FOR_TRIAL_START:
            if self.task_type == 'simpleConditioning':
                self.gpio.led_center_off()
                self._transition_to(TrialState.CLICKS_ON)
            else:
                self._transition_to(TrialState.WAIT_FOR_CPOKE)
        
        elif self.current_state == TrialState.WAIT_FOR_CPOKE:
            if self.gpio.is_central_poke_active():
                self.cpoke_press_start_time = current_time
                self.log_event('cpoke_in')
                self._transition_to(TrialState.CPOKE_IN)
                
        elif self.current_state == TrialState.CPOKE_IN:
            if not self.gpio.is_central_poke_active():
                #Pulled out
                self.violated = True
                self.log_event('break', {'duration': time_in_state})
                self.log_event('cpoke_out', {'duration': time_in_state})
                self._transition_to(TrialState.WAIT_FOR_CPOKE)
            elif current_time - self.cpoke_press_start_time >= self.central_poke_required_time:
                #Held long enough
                self.cpoke_req_end_time = current_time
                self.cpoke_out_time = current_time
                self.log_event('cpoke_req_end', {'duration': time_in_state})
                self.log_event('cpoke_out', {'duration': time_in_state})
                self.gpio.led_center_off()
                self._transition_to(TrialState.CLICKS_ON)
                
        elif self.current_state == TrialState.CLICKS_ON:
            #Wait for background audio thread to finish
            if self.audio_completed:
                self._transition_to(TrialState.WAIT_FOR_SPOKE)
                
        elif self.current_state == TrialState.STIMULATION:
            pass
            
        elif self.current_state == TrialState.WAIT_FOR_SPOKE:
            if self.gpio.is_left_port_active():
                self._handle_spoke('left', 'L', TrialState.LEFT_REWARD)
            elif self.gpio.is_right_port_active():
                self._handle_spoke('right', 'R', TrialState.RIGHT_REWARD)
                
        elif self.current_state == TrialState.LEFT_REWARD:
            if not self.reward_delivered:
                self.gpio.deliver_reward_async_left()
                self.log_event('left_reward')
                self.reward_delivered = True
            elif time_in_state >= 0.2:
                self._transition_to(TrialState.TRIAL_END)
                
        elif self.current_state == TrialState.RIGHT_REWARD:
            if not self.reward_delivered:
                self.gpio.deliver_reward_async_right()
                self.log_event('right_reward')
                self.reward_delivered = True
            elif time_in_state >= 0.2:
                self._transition_to(TrialState.TRIAL_END)
                
        elif self.current_state == TrialState.ERROR:
            if time_in_state >= 0.2:
                self._transition_to(TrialState.TRIAL_END)
                
        elif self.current_state == TrialState.TRIAL_END:
            self._end_trial()
            return False
            
        return True

    
    def _handle_spoke(self, port_name, choice_char, target_reward_state):
        self.responded = True
        self.choice = choice_char
        if self.cpoke_out_time:
            self.response_time_s = time.time() - self.cpoke_out_time
            
        self.log_event('spoke', {'port': port_name, 'response_time': self.response_time_s})
        
        if self.reward_side == choice_char:
            self._transition_to(target_reward_state)
        else:
            
            self._transition_to(TrialState.ERROR)

    def _transition_to(self, new_state):
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = time.time()
        self.reward_delivered = False
        
        self.log_event('STATE_TRANSITION', {
            'from': old_state.name,
            'to': new_state.name
        })
        
    def _handle_state_timeout(self):
        self.log_event('STATE_TIMEOUT', {'state': self.current_state.name})
        if self.current_state == TrialState.WAIT_FOR_CPOKE:
            self._transition_to(TrialState.TRIAL_END)
        elif self.current_state == TrialState.WAIT_FOR_SPOKE:
            self.log_event('NO_PORT_RESPONSE')
            self._transition_to(TrialState.TRIAL_END)
            
    def _click_scheduler(self):
        idx_L = 0
        idx_R = 0
        len_L = len(self.click_times_left)
        len_R = len(self.click_times_right)
        
        while self.running and not self.completed:
            if self.current_state in [TrialState.CLICKS_ON, TrialState.STIMULATION]:
                current_time = time.time() - self.state_start_time
                
                #Check Left Clicks
                if idx_L < len_L and current_time >= self.click_times_left[idx_L]:
                    self.audio.play_click_left()
                    self.log_event('CLICK_LEFT', {'time': current_time})
                    idx_L += 1
                    
                #Check Right Clicks
                if idx_R < len_R and current_time >= self.click_times_right[idx_R]:
                    self.audio.play_click_right()
                    self.log_event('CLICK_RIGHT', {'time': current_time})
                    idx_R += 1
                    
                #Check if all audio is finished
                if idx_L >= len_L and idx_R >= len_R:
                    time.sleep(0.1) # Small buffer after last click
                    self.log_event('clicks_off')
                    
                    #Flag
                    self.audio_completed = True 
                    break
                    
            time.sleep(0.001)
    
