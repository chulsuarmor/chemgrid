# Skill: PDF Generation

## reportlab PDF Generation
- Use `reportlab` for PDF creation (`SimpleDocTemplate`, `Paragraph`, `Table`, etc.)
- Register Korean font: `pdfmetrics.registerFont(TTFont('MalgunGothic', 'malgun.ttf'))`
- Fallback font paths (Windows): `C:/Windows/Fonts/malgun.ttf`, `C:/Windows/Fonts/malgunbd.ttf`
- Always wrap font registration in try/except for environments where malgun.ttf is missing

## RDKit Molecule Rendering for PDF
- `atomLabelFontSize` attribute may not exist in all RDKit versions
- Always wrap in `try/except AttributeError` for compatibility:
  ```python
  try:
      drawer.SetFontSize(font_size)
  except AttributeError:
      pass
  ```

## Key Classes in OWNED_FILES
- `ExportManager` (export_manager_enhanced.py): Main export orchestrator, requires canvas_widget
- `ExportDialog`: PyQt6 dialog for export options
- `IntegratedPDFExporter`: reportlab-based multi-page PDF with structure images
- `SelectionExporter`: Exports selected atoms/bonds
- `ChemFileManager`: .chemgrid file save/load
- `MechanismPDFExporter` (mechanism_pdf_exporter.py): Retrosynthesis route PDF export

## PNG Export
- Default 300 DPI for high-resolution output
- User-adjustable via ExportDialog

## XYZ Format
- Line 1: atom count
- Line 2: comment (molecule name / SMILES)
- Lines 3+: `Element x y z` in Angstroms
