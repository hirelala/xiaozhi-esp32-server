#!/bin/bash

set -e

echo "V2V LiveKit Proxy Server Setup"
echo "==============================="
echo ""

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Setup complete!"
echo ""

if [ ! -f ".env" ]; then
    echo "No .env file found. Creating from template..."
    cp env.template .env
    echo "Please edit .env with your LiveKit credentials"
    echo ""
fi

echo "To start the server:"
echo "  1. Edit .env with your LiveKit credentials"
echo "  2. source venv/bin/activate"
echo "  3. export \$(cat .env | xargs)"
echo "  4. cd src"
echo "  5. python main.py"
echo ""
echo "Server will listen on: ws://0.0.0.0:8765/v2v"
echo ""
