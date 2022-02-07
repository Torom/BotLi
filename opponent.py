from datetime import datetime


class Opponent:
    def __init__(self, username: str, release_time: datetime = datetime.now(), multiplier: int = 1) -> None:
        self.username = username
        self.release_time = release_time
        self.multiplier = multiplier

    @classmethod
    def from_dict(cls, dict_: dict):
        username = dict_['username']
        release_time = datetime(
            dict_['release_time']['year'],
            dict_['release_time']['month'],
            dict_['release_time']['day'],
            dict_['release_time']['hour'],
            dict_['release_time']['minute'])
        multiplier = dict_['multiplier']

        return Opponent(username, release_time, multiplier)

    def __dict__(self) -> dict:
        return {'username': self.username,
                'release_time':
                {'year': self.release_time.year, 'month': self.release_time.month,
                 'day': self.release_time.day, 'hour': self.release_time.hour,
                 'minute': self.release_time.minute},
                'multiplier': self.multiplier}

    def __eq__(self, o: object) -> bool:
        if isinstance(o, Opponent):
            return self.username == o.username
        else:
            raise NotImplemented
