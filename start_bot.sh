#!/bin/bash
# PainfulBot restart — delegates to systemd so only one instance ever runs.
# Usage: ./start_bot.sh

echo "Restarting PainfulIT bot via systemd..."
sudo systemctl restart PainfulIT-bot.service

echo ""
echo "Done. One instance running under systemd."
echo "Tail logs: sudo journalctl -u PainfulIT-bot.service -f"
