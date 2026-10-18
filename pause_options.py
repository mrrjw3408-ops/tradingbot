p = "agents/options_paper.py"
s = open(p).read()
marker = "def log_trade(trade):\n"
if "OPTIONS_PAPER_PAUSED" in s:
    raise SystemExit("Already patched - nothing changed")
if s.count(marker) != 1:
    raise SystemExit('Could not find exactly one "def log_trade(trade):" - nothing changed')
new = (
    "OPTIONS_PAPER_PAUSED = True  # set to False to resume logging new paper options trades\n\n"
    + marker
    + "    if OPTIONS_PAPER_PAUSED:\n"
    + '        print("Options paper trading is paused - trade not logged")\n'
    + "        return None\n"
)
open(p, "w").write(s.replace(marker, new))
print("Patched: new paper options trades will no longer be logged")
