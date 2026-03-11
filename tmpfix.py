# step1
TARGET="c:/chemgrid/src/app/popup_predicted_spectrum.py"
with open(TARGET,encoding="utf-8") as r: lines=r.readlines()
new_ir=open("c:/chemgrid/new_ir.txt",encoding="utf-8").read()
new_ir_lines=new_ir.splitlines(keepends=True)+["\n"]
