import os
import sys

def get_path(path:str):
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        if sys._MEIPASS is not None:
            icon_path = os.path.join(sys._MEIPASS, path)
        else:
            icon_path = os.path.join(os.path.dirname(sys.executable), path)
            if not os.path.exists(icon_path):
                icon_path = os.path.join(os.getcwd(), path)
    else:
        # Running as Python script
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    return icon_path