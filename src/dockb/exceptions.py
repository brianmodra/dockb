class EditTextRangeError(Exception):
    def __init__(self, message: str, start: int, end:int):
        super(message)
        self.start = start
        self.end = end