def parse_time_control(time_control: str) -> tuple[int, int]:
    initial_time_str, increment_str = time_control.split("+")
    initial_time = int(float(initial_time_str) * 60)
    increment = int(increment_str)
    return initial_time, increment

def validate_time_limits(initial: int, increment: int, min_initial: int, max_initial: int,   
                        min_increment: int, max_increment: int) -> tuple[bool, str | None]:  
    if increment < min_increment:  
        return False, f'Increment {increment} is too short according to config.'  
      
    if increment > max_increment:  
        return False, f'Increment {increment} is too long according to config.'  
      
    if initial < min_initial:  
        return False, f'Initial time {initial} is too short according to config.'  
      
    if initial > max_initial:  
        return False, f'Initial time {initial} is too long according to config.'  
      
    return True, None  

def validate_config_section(config: dict, section_name: str, required_fields: list[list]) -> None:    
    for field_info in required_fields:    
        field_name, field_type, error_msg = field_info  
        if field_name not in config:    
            raise RuntimeError(f'Your config does not have required `{section_name}` subsection `{field_name}`.')    
            
        if not isinstance(config[field_name], field_type):    
            raise TypeError(f'`{section_name}` subsection {error_msg}')
