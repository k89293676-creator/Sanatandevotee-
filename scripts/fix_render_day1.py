p = "scripts/render_day1.py"
s = open(p, encoding="utf-8").read()
s = s.replace("if mp4:\n    \n", 'if mp4:\n    print("validate:", render.validate(mp4))\n')
open(p, "w", encoding="utf-8").write(s)
print("done")