#!/usr/bin/env python3
"""SessionStart note: offer once to set up the server list, unless the user declined."""
import os

folder = os.path.expanduser("~/.config/cehr-dev")
if not any(os.path.exists(os.path.join(folder, name)) for name in ("servers.json", "declined")):
    print("cehr-dev: there is no server list yet, so every direct ssh is blocked. Offer once, in a line or "
          "two, to set one up with the run-on-server skill. If the user wants none of this, they turn the "
          "guard off themselves with `mkdir -p ~/.config/cehr-dev && touch ~/.config/cehr-dev/declined`.")
