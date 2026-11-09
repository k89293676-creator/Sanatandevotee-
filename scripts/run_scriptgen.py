import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from src.factory import scriptgen
print(scriptgen.run("shiv_chalisa"))