def parse_time_control(time_control: str) -> tuple[int, int]:
    initial_time_str, increment_str = time_control.split('+')
    initial_time = int(float(initial_time_str) * 60)
    increment = int(increment_str)
    return initial_time, increment
