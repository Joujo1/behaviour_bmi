import json

class TrialParametersParser:
    """
    Parses trial parameter strings from UDP commands using standard JSON.
    Expected format:
    START_TRIAL:{"states": {"wait_for_cpoke": 10.0, "cpoke_in": 2.0}, "clickTimesR": [0.1, 0.2], "side": "L", "task": "simpleConditioning", "centralPokeTime": 0.5}
    """
    
    STATE_NAME_MAP = {
        'wait_for_trial_start': 0,
        'wait_for_cpoke': 1,
        'cpoke_in': 2,
        'clicks_on': 3,
        'stimulation': 4,
        'wait_for_spoke': 5,
        'left_reward': 6,
        'right_reward': 7,
        'error': 8,
        'trial_end': 10
    }
    
    @staticmethod
    def parse(command_string):
        """
        Parse trial parameters from a JSON command string.
        """
        try:
            prefix = "START_TRIAL:"
            if not command_string.startswith(prefix):
                print(f"Invalid command format. Expected '{prefix}'")
                return None
            
            json_payload = command_string[len(prefix):].strip()
            raw_params = json.loads(json_payload)

            params = {
                'clickTimesR': raw_params.get('clickTimesR', []),
                'clickTimesL': raw_params.get('clickTimesL', []),
                'side': str(raw_params.get('side', 'L')).upper(),
                'task': str(raw_params.get('task', 'simpleConditioning')),
                'centralPokeTime': float(raw_params.get('centralPokeTime', 0.5)),
                'states': {}
            }
            
            if 'states' in raw_params and isinstance(raw_params['states'], dict):
                for state_name, max_time in raw_params['states'].items():
                    s_name = state_name.lower()
                    if s_name in TrialParametersParser.STATE_NAME_MAP:
                        state_id = TrialParametersParser.STATE_NAME_MAP[s_name]
                        #Store as a direct Key:Value pair -> {1: 10.0, 2: 2.0}
                        params['states'][state_id] = float(max_time)
                    else:
                        print(f"Warning: Unknown state name '{state_name}'")
                        
            return params
            
        except json.JSONDecodeError as e:
            print(f"JSON Parsing Error: The PC sent malformed JSON. {e}")
            return None
        except Exception as e:
            print(f"Unexpected error parsing parameters: {e}")
            return None
    
    @staticmethod
    def validate_parameters(params):
        if not params:
            return False, "No parameters provided"
        
        # Validate side
        if params.get('side') not in ['L', 'R']:
            return False, f"Invalid side: {params.get('side')} (must be L or R)"
        
        # Validate task
        valid_tasks = ['simpleConditioning', 'initiation']
        if params.get('task') not in valid_tasks:
            return False, f"Invalid task: {params.get('task')} (must be one of {valid_tasks})"
        
        # Validate click times are sorted (Important for the audio scheduler)
        for side in ['clickTimesL', 'clickTimesR']:
            times = params.get(side, [])
            if len(times) > 1 and times != sorted(times):
                return False, f"{side} must be in ascending temporal order"
        
        # Validate states dictionary
        for state_id, max_time in params.get('states', {}).items():
            if not (0 <= state_id <= 10):
                return False, f"Invalid state number: {state_id} (must be 0-10)"
            if max_time < 0:
                return False, f"Invalid max time for state {state_id}: {max_time}"
        
        return True, "Valid"