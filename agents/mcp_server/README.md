# Gemini MCP Server for ChemGrid

This MCP server provides AI-powered chemical structure analysis and drawing automation tools for ChemGrid.

## Features

- **Image Analysis**: Analyze screenshots of chemical structures using Google Gemini 1.5 Flash.
- **Drawing Automation**: Simulate mouse interactions to draw molecules on the ChemGrid canvas.
- **Molecule Database**: Built-in complexity levels (1-10) for guided learning.
- **SMILES Validation**: Verify drawn structures against target SMILES.

## Setup

1. **Install Dependencies**
   Open a terminal in the project root and run:
   ```bash
   pip install -r agents/mcp_server/requirements.txt
   ```
   *(Note: RDKit is currently disabled due to compatibility issues with Python 3.14. String comparison is used for validation.)*

2. **Configure API Key**
   - Create a `.env` file in `agents/mcp_server` (copy from `.env.example`).
   - Add your Google Gemini API key: `GOOGLE_API_KEY=your_key_here`

## Usage

### 1. Start the Server manually
```bash
python agents/mcp_server/server.py
```
The server runs at `http://127.0.0.1:8000`.

### 2. Run the AI Tutor (Automated Training)
This script acts as an AI agent that connects to the MCP server and performs the drawing tasks step-by-step.
```bash
python _chemgrid_tutor.py
```

## API Endpoints

- `POST /analyze_image`: Upload an image to get SMILES and description.
- `POST /canvas/reset`: Reset the drawing canvas.
- `POST /draw/click`: Click at specific grid coordinates.
- `POST /draw/drag`: Drag mouse from start to end coordinates.
- `POST /tools/select`: Select a tool (bond, element, ring, etc.).
- `POST /molecule/generate`: Get target molecule info for a specific level (1-10).
- `POST /validate/smiles`: Compare current SMILES with target SMILES.

## Complexity Levels

The system supports 10 levels of increasing complexity:
1. Water (Simple placement)
2. Ethanol (Single bonds)
...
4. Cyclopentadienyl Radical (Rings + Radicals)
6. Tropylium Ion (Charges)
...
10. Heme B Core (Complex macrocycle)
