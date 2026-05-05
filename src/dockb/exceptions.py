class EditTextRangeError(Exception):
    def __init__(self, message: str, start: int, end: int):
        super().__init__(message)
        self.start = start
        self.end = end
