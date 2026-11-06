import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "kicad-command-palette"))
from kicad_palette import main

main()
