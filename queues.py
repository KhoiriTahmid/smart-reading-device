import queue

motor_queue   = queue.Queue()  # commands: "full","slow","stop","forward","backward"
ocr_queue     = queue.Queue()  # commands: "start"
speaker_queue = queue.Queue()  # commands: sound name strings