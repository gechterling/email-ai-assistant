#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
SERVICE_NAME="email-ai-assistant"

echo "=== Email AI Assistant Installer ==="
echo ""

# Check Python 3.9+
python3 -c "import sys; assert sys.version_info >= (3,9), 'Python 3.9+ required'" || {
  echo "ERROR: Python 3.9 or higher is required."
  exit 1
}

echo "Creating virtual environment..."
python3 -m venv "$VENV"

echo "Installing dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$DIR/requirements.txt"

echo "Setting up systemd service..."
SERVICE_FILE="$HOME/.config/systemd/user/$SERVICE_NAME.service"
mkdir -p "$(dirname "$SERVICE_FILE")"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Email AI Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$VENV/bin/python $DIR/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "The service is now running at: http://127.0.0.1:7890"
echo ""
echo "Useful commands:"
echo "  View logs:    journalctl --user -u $SERVICE_NAME -f"
echo "  Stop:         systemctl --user stop $SERVICE_NAME"
echo "  Restart:      systemctl --user restart $SERVICE_NAME"
echo "  Status:       systemctl --user status $SERVICE_NAME"
echo ""
echo "Next steps:"
echo "  1. Open http://127.0.0.1:7890 in your browser"
echo "  2. Go to Settings and enter your IMAP credentials"
echo "  3. Go to Writing Style and click 'Analyze My Sent Emails'"
echo "  4. Add keywords on the Dashboard and click 'Analyze & Draft Replies'"
echo ""
