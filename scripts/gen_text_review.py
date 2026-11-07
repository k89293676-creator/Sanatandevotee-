import json
vs = json.load(open("data/packs/shiv_chalisa/verses.json", encoding="utf-8"))
lines = ["# Shiv Chalisa Verse Text (for verification)", ""]
for v in vs:
    lines.append("## %d. (%s)" % (v["seq"], v["kind"]))
    lines.append(v["devanagari"])
    lines.append("*%s*" % v["roman"])
    lines.append("Hindi: %s" % v["meaning_hi"])
    lines.append("")
open("docs/TEXT_REVIEW.md", "w", encoding="utf-8").write("\n".join(lines))
print("written", len(vs))